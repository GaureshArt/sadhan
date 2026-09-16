from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import config
from .llms import registry, discover
from .llms.client import LiteLLMClient, chunk_reasoning, chunk_text, chunk_usage_tokens
from .state import add_message
from .tools import TOOLS

client = LiteLLMClient()


class LlmError(RuntimeError):
    pass


@dataclass
class Turn:
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)


def _delta_tool_calls(chunk) -> list:
    choices = getattr(chunk, "choices", None)
    if not choices:
        return []
    choice = choices[0]
    delta = getattr(choice, "delta", None)
    if delta is not None:
        return list(getattr(delta, "tool_calls", None) or [])
    message = getattr(choice, "message", None)
    return list(getattr(message, "tool_calls", None) or [])


def _accumulate_tool_calls(acc: list[dict], tool_calls: list) -> None:
    for tc in tool_calls:
        index = getattr(tc, "index", None)
        if index is None:
            index = len(acc)
        while len(acc) <= index:
            acc.append({"id": None, "name": None, "arguments": ""})
        slot = acc[index]
        if getattr(tc, "id", None):
            slot["id"] = tc.id
        fn = getattr(tc, "function", None)
        if fn is None:
            continue
        if getattr(fn, "name", None):
            slot["name"] = fn.name
        args = getattr(fn, "arguments", None)
        if args:
            slot["arguments"] += json.dumps(args) if not isinstance(args, str) else args


def _finalize_tool_calls(acc: list[dict]) -> list[dict]:
    calls = []
    for i, slot in enumerate(acc):
        if slot["name"] is None and not slot["arguments"]:
            continue
        calls.append(
            {
                "id": slot["id"] or f"call_{i}",
                "name": slot["name"] or "run_bash",
                "arguments": slot["arguments"] or "",
            }
        )
    return calls


_TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


def _extract_inline_tool_calls(text: str) -> tuple[list[dict], list[tuple[int, int]]]:
    decoder = json.JSONDecoder()
    calls = []
    ranges = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        name = obj.get("name") if isinstance(obj, dict) else None
        arguments = obj.get("arguments") if isinstance(obj, dict) else None
        if isinstance(name, str) and name in _TOOL_NAMES and isinstance(arguments, (dict, str)):
            if isinstance(arguments, str):
                args = {"command": arguments}
            else:
                args = arguments
            calls.append({"name": name, "arguments": json.dumps(args)})
            ranges.append((i, end))
            i = end
            continue
        i += 1
    return calls, ranges


def _strip_inline_calls(text: str, ranges: list[tuple[int, int]]) -> str:
    out = []
    last = 0
    for start, end in sorted(ranges):
        out.append(text[last:start])
        last = end
    out.append(text[last:])
    cleaned = "".join(out)
    cleaned = cleaned.replace("<tool_call>", "").replace("</tool_call>", "")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _unwrap_text_wrapper(text: str) -> str:
    stripped = (text or "").strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return text
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    arguments = obj.get("arguments")
    if isinstance(obj, dict) and isinstance(obj.get("name"), str) and isinstance(arguments, dict):
        for value in arguments.values():
            if isinstance(value, str):
                return value.strip()
    return text


def _short(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return _short(lines[-1]) if lines else ""


def _reason_from_arguments(arguments: str) -> str:
    try:
        parsed = json.loads((arguments or "").strip())
    except json.JSONDecodeError:
        return ""
    if isinstance(parsed, dict):
        reason = parsed.get("reason")
        if isinstance(reason, str):
            return _short(reason)
    return ""


class _ReasonStream:
    """Streams model text live, hiding inline tool-call JSON from the display."""

    def __init__(self, emit):
        self._emit = emit
        self._buf = ""

    @staticmethod
    def _clean(text: str) -> str:
        return text.replace("<tool_call>", " ").replace("</tool_call>", " ")

    def feed(self, text: str) -> None:
        self._buf += text
        self._process()

    def flush(self) -> None:
        self._process()

    def _process(self) -> None:
        marker = self._buf.find('{"name"')
        if marker < 0:
            self._flush_all()
            return
        pre = self._buf[:marker]
        try:
            obj, end = json.JSONDecoder().raw_decode(self._buf, marker)
            complete = True
        except json.JSONDecodeError:
            complete = False
        if complete:
            name = obj.get("name") if isinstance(obj, dict) else None
            arguments = obj.get("arguments") if isinstance(obj, dict) else None
            if isinstance(name, str) and name in _TOOL_NAMES and isinstance(arguments, (dict, str)):
                if pre.strip():
                    self._emit({"type": "reasoning_token", "text": self._clean(pre)})
                self._buf = self._buf[end:]
                self._process()
                return
            self._flush_all()
            return
        if pre.strip():
            self._emit({"type": "reasoning_token", "text": self._clean(pre)})
        self._buf = self._buf[marker:]

    def _flush_all(self) -> None:
        if self._buf.strip():
            self._emit({"type": "reasoning_token", "text": self._clean(self._buf)})
        self._buf = ""


async def llm_call(state, emit, tools=None):
    discover(default_model=config.model)
    model = registry.active
    if model is None:
        raise RuntimeError("no model available; is Ollama running or an API key set?")

    stream = client.stream_chat(state["messages"], model=model, tools=tools or TOOLS)

    prose = []
    thought = []
    tool_acc = []
    usage = None
    streamer = _ReasonStream(emit)

    async for chunk in stream:
        chunk_tokens = chunk_usage_tokens(chunk)
        if chunk_tokens is not None:
            usage = chunk_tokens
        delta = chunk_reasoning(chunk)
        if delta:
            thought.append(delta)
            streamer.feed(delta)
        delta = chunk_text(chunk)
        if delta:
            prose.append(delta)
            streamer.feed(delta)
        _accumulate_tool_calls(tool_acc, _delta_tool_calls(chunk))
    streamer.flush()

    if usage is not None:
        emit({"type": "usage", "tokens": usage})

    prose_text = "".join(prose)
    thought_text = "".join(thought)

    tool_calls = _finalize_tool_calls(tool_acc)

    if not tool_calls:
        inline_calls, prose_ranges = _extract_inline_tool_calls(prose_text)
        more_calls, thought_ranges = _extract_inline_tool_calls(thought_text)
        prose_text = _strip_inline_calls(prose_text, prose_ranges)
        thought_text = _strip_inline_calls(thought_text, thought_ranges)
        seen = set()
        for call in inline_calls + more_calls:
            key = (call["name"], call["arguments"])
            if key in seen:
                continue
            seen.add(key)
            tool_calls.append({"id": f"call_{len(tool_calls)}", "name": call["name"], "arguments": call["arguments"]})

    fallback = _last_line(prose_text) or _last_line(thought_text)
    for call in tool_calls:
        if call["name"] in _TOOL_NAMES:
            call["reason"] = _reason_from_arguments(call["arguments"]) or fallback

    text = _unwrap_text_wrapper(prose_text.strip())

    if not tool_calls and not text.strip():
        raise LlmError("model returned an empty response with no tool call")

    if tool_calls:
        add_message(
            state,
            role="assistant",
            content=text,
            tool_calls=[
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {"name": call["name"], "arguments": call["arguments"]},
                }
                for call in tool_calls
            ],
        )
    else:
        add_message(state, role="assistant", content=text)

    return Turn(content=text, tool_calls=tool_calls)