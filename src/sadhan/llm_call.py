from . import config
from .llms import registry, discover
from .llms.client import LiteLLMClient, chunk_text, chunk_usage_tokens
from .state import add_message
from .parser import parser

client = LiteLLMClient()

TAGS = ('<reasoning>', '</reasoning>', '<action>', '</action>')


async def llm_call(state, emit):
    discover(default_model=config.model)
    model = registry.active
    if model is None:
        raise RuntimeError("no model available; is Ollama running or an API key set?")

    stream = client.stream_chat(state['messages'], model=model)

    content = []
    pos = 0
    seg_start = 0
    mode = 'pre'
    action_parts = []
    holdback = max(len(t) for t in TAGS) - 1
    usage = None

    def flush_segment(end):
        nonlocal seg_start
        text = ''.join(content)[seg_start:end]
        if mode == 'reasoning' and text:
            emit({'type': 'reasoning_token', 'text': text})
        elif mode == 'action':
            action_parts.append(text)
        seg_start = end

    def process(final):
        nonlocal pos, mode, seg_start
        text = ''.join(content)
        limit = len(text) if final else len(text) - holdback
        while pos < limit:
            tag = next((t for t in TAGS if text.startswith(t, pos)), None)
            if tag is not None:
                flush_segment(pos)
                if tag == '<reasoning>':
                    mode = 'reasoning'
                elif tag == '</reasoning>':
                    mode = 'post'
                elif tag == '<action>':
                    mode = 'action'
                elif tag == '</action>':
                    if mode == 'action':
                        emit({'type': 'action', 'command': ''.join(action_parts).strip()})
                    mode = 'done'
                pos += len(tag)
                seg_start = pos
                continue
            if text[pos] == '<' and not final:
                if any(t.startswith(text[pos:]) for t in TAGS):
                    break
            pos += 1

    async for chunk in stream:
        chunk_tokens = chunk_usage_tokens(chunk)
        if chunk_tokens is not None:
            usage = chunk_tokens
        delta = chunk_text(chunk)
        if delta:
            content.append(delta)
            process(final=False)

    process(final=True)

    if usage is not None:
        emit({'type': 'usage', 'tokens': usage})

    full = ''.join(content)
    add_message(state, role='assistant', content=full)
    return parser(full)
