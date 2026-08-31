from ollama import AsyncClient
from .config import model
from .state import add_message
from .parser import parser

client = AsyncClient()

TAGS = ('<reasoning>', '</reasoning>', '<action>', '</action>')


async def llm_call(state, emit):
    stream = await client.chat(
        model=model,
        messages=state['messages'],
        think=False,
        stream=True,
    )

    content = []
    pos = 0
    seg_start = 0
    mode = 'pre'
    action_parts = []
    holdback = max(len(t) for t in TAGS) - 1
    last_chunk = None

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
        last_chunk = chunk
        delta = chunk['message']['content']
        if delta:
            content.append(delta)
            process(final=False)

    process(final=True)

    if last_chunk is not None:
        tokens = last_chunk.get('eval_count', 0) + last_chunk.get('prompt_eval_count', 0)
        emit({'type': 'usage', 'tokens': tokens})

    full = ''.join(content)
    add_message(state, role='assistant', content=full)
    return parser(full)