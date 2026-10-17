from collections.abc import Callable
import json
from logging import getLogger
from typing import Any
from uuid import uuid4

from litellm import acompletion, stream_chunk_builder

from .messages import Block, Message, TextBlock, ToolResultBlock, ToolUseBlock

logger = getLogger(__name__)

TextCallback = Callable[[str],None]


class Provider:
    async def chat(self, messages: list[Message], tools: list[dict], system_prompt: str | None,on_text_delta:TextCallback | None = None) -> Message:
        raise NotImplementedError


class LiteLLMProvider(Provider):
    def __init__(self, model: str, api_base: str | None = None) -> None:
        self.model: str = model
        self.api_base: str | None = api_base or None

    def _assistant_to_wire(self, message: Message) -> dict:
        wire: dict = {"role": "assistant", "content": message.text}
        if message.tool_uses:
            wire["tool_calls"] = [
                {
                    "id": t.id,
                    "type": "function",
                    "function": {"name": t.name, "arguments": json.dumps(t.input)},
                }
                for t in message.tool_uses
            ]
        return wire

    def _user_to_wire(self, message: Message) -> list[dict]:
        wire = []
        for block in message.content:
            if isinstance(block, ToolResultBlock):
                wire.append({"role": "tool", "tool_call_id": block.tool_use_id, "content": block.content})
        if message.text:
            wire.append({"role": "user", "content": message.text})

        return wire

    def _to_wire(self, messages: list[Message], system_prompt: str | None) -> list[dict]:
        wire: list[dict] = []
        if system_prompt:
            wire.append({"role": "system", "content": system_prompt})
        for message in messages:
            if message.role == "assistant":
                wire.append(self._assistant_to_wire(message))
            else:
                wire.extend(self._user_to_wire(message))
        return wire

    def _from_response(self, response: Any) -> Message:
        msg = response.choices[0].message
        blocks: list[Block] = []
        if msg.content:
            blocks.append(TextBlock(text=msg.content))
        for call in msg.tool_calls or []:
            blocks.append(
                ToolUseBlock(
                    id=call.id or uuid4().hex,
                    name=call.function.name,
                    input=self._parse_arguments(call.function.arguments),
                )
            )
        return Message(role="assistant", content=blocks)

    def _parse_arguments(self, raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid tool arguments from model: %r", raw)
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def chat(self, messages: list[Message], tools: list[dict], system_prompt: str | None,on_text_delta:TextCallback | None = None) -> Message:
        wire = self._to_wire(messages=messages, system_prompt=system_prompt)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": wire,
            "stream":True
        }
        chunks = []
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if tools:
            kwargs["tools"] = tools
        kwargs["reasoning_effort"] = "none"
        async for chunk in await acompletion(**kwargs):
            chunks.append(chunk)
            if on_text_delta and chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    on_text_delta(delta)
        response = stream_chunk_builder(chunks,messages=wire)

        if response is None:
            raise RuntimeError("Model returned an empty stream")
        return self._from_response(response)
