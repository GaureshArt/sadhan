from .config import step_limit,max_errors,cwd
def init_state():
    return {
        "messages": [],
        "n_calls": 0,
        "step_limit": step_limit,
        "n_errors": 0,
        "max_errors": max_errors,
        "cwd": cwd,
    }

def add_message(state, role, content):
    state['messages'].append({
        'role':role,
        'content':content
    })