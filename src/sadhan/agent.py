import asyncio

from .state import add_message, init_state
from .bash import run_bash_command
from .prompt import system_prompt
from .llm_call import llm_call


def print_event(event):
    t = event['type']
    if t == 'reasoning_token':
        print(event['text'], end='', flush=True)
    elif t == 'action':
        print(f"\n$ {event['command']}")
    elif t == 'result':
        print(f"\nBash Result \n returncode:{event['returncode']} \n output:{event['output']}")
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
    response = await llm_call(state, emit)
    if response['action'] != 'echo TASK_COMPLETE':
        action_response = await run_bash_command(response['action'])
        emit({'type': 'result', 'returncode': action_response['returncode'], 'output': action_response['output']})
        add_message(state, role='user', content=f"Bash Result \n returncode:{action_response['returncode']} \n output:{action_response['output']}")
    return response


async def agent(task, emit=print_event, state=None):
    if state is None:
        state = init_state()
    else:
        state['n_calls'] = 0
        state['n_errors'] = 0

    if not any(m['role'] == 'system' for m in state['messages']):
        add_message(state, role='system', content=system_prompt)
    add_message(state, role='user', content=task)

    try:
        while True:
            if state['n_calls'] >= state['step_limit']:
                emit({'type': 'status', 'status': 'stopped', 'reason': 'step limit reached'})
                return {"status": "stopped", "reason": "step_limit"}
            if state['n_errors'] >= state['max_errors']:
                emit({'type': 'status', 'status': 'stopped', 'reason': 'too many errors'})
                return {"status": "stopped", "reason": "max_errors"}
            try:
                output = await step(state, emit)
                if output['action'] == 'echo "TASK_COMPLETE"':
                    emit({'type': 'status', 'status': 'complete'})
                    return {"status": "complete"}
            except Exception as e:
                state['n_errors'] += 1
                emit({'type': 'error', 'message': str(e)})
                add_message(state, role='user', content=f"Agent error : {e}")
            finally:
                state['n_calls'] += 1
    except asyncio.CancelledError:
        emit({'type': 'status', 'status': 'cancelled'})
        raise