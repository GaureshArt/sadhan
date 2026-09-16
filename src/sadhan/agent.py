import asyncio

from .state import add_message, init_state
from .llm_call import LlmError, llm_call
from .prompt import system_prompt
from .sessions import flush_session
from .tools import BASH_TOOL, RunBash, parse_command, run_bash_tool


def print_event(event):
    t = event['type']
    if t == 'reasoning_token':
        print(event['text'], end='', flush=True)
    elif t == 'action':
        print(f"\n$ {event['command']}")
    elif t == 'reason':
        print(f"\n✦ {event['text']}")
    elif t == 'result':
        print(f"\nBash Result \n returncode:{event['returncode']} \n output:{event['output']}")
    elif t == 'answer':
        print(f"\n{event['text']}")
    elif t == 'error':
        print(f"Agent error : {event['message']}")
    elif t == 'status':
        if event.get('status') == 'complete':
            print("Task complete")
        elif event.get('status') == 'stopped':
            print(f"Agent stopped : {event['reason']}")
        elif event.get('status') == 'cancelled':
            print("Agent cancelled")


async def step(state, emit):
    turn = await llm_call(state, emit)

    if not turn.tool_calls:
        if turn.content.strip():
            emit({'type': 'answer', 'text': turn.content.strip()})
        return {"status": "complete"}

    for call in turn.tool_calls:
        if call["name"] != BASH_TOOL:
            add_message(
                state, "tool",
                f"[UNKNOWN TOOL] no tool named {call['name']!r}; re-read the tool schema.",
                tool_call_id=call["id"],
            )
            emit({'type': 'error', 'message': f"unknown tool call: {call['name']}"})
            continue
        try:
            command = parse_command(call["arguments"])
        except ValueError as e:
            add_message(
                state, "tool",
                f"[TOOL CALL ERROR] {e}. Call run_bash with valid arguments matching this schema: {RunBash.model_json_schema()}",
                tool_call_id=call["id"],
            )
            emit({'type': 'error', 'message': f"invalid tool call: {e}"})
            continue
        reason = call.get("reason") or ""
        if reason:
            emit({'type': 'reason', 'text': reason})
        emit({'type': 'action', 'command': command})
        try:
            result = await run_bash_tool(call["arguments"])
        except Exception as e:
            result = {"returncode": -1, "output": f"[ERROR] {e}"}
        body = f"Bash Result \n returncode:{result['returncode']} \n output:{result['output']}"
        add_message(state, "tool", body, tool_call_id=call["id"])
        emit({'type': 'result', 'returncode': result['returncode'], 'output': result['output']})

    flush_session(state)
    return {"status": "step"}


async def agent(task, emit=print_event, state=None):
    if state is None:
        state = init_state()
    else:
        state['n_calls'] = 0
        state['n_errors'] = 0

    if not any(m['role'] == 'system' for m in state['messages']):
        add_message(state, role='system', content=system_prompt)
    add_message(state, role='user', content=task)
    flush_session(state)

    try:
        while True:
            if state['n_calls'] >= state['step_limit']:
                emit({'type': 'status', 'status': 'stopped', 'reason': 'step limit reached'})
                return {"status": "stopped", "reason": "step_limit"}
            if state['n_errors'] >= state['max_errors']:
                emit({'type': 'status', 'status': 'stopped', 'reason': 'too many errors'})
                return {"status": "stopped", "reason": "max_errors"}
            try:
                outcome = await step(state, emit)
                if outcome.get('status') == 'complete':
                    emit({'type': 'status', 'status': 'complete'})
                    return {"status": "complete"}
            except LlmError as e:
                state['n_errors'] += 1
                emit({'type': 'error', 'message': str(e)})
                add_message(state, role='user', content=f"[MODEL ERROR] {e}. Continue the task and retry with a valid response.")
            except Exception as e:
                state['n_errors'] += 1
                emit({'type': 'error', 'message': str(e)})
                add_message(state, role='user', content=f"Agent error : {e}")
            finally:
                state['n_calls'] += 1
                flush_session(state)
    except asyncio.CancelledError:
        emit({'type': 'status', 'status': 'cancelled'})
        raise