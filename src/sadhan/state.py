from .config import step_limit, max_errors, cwd

def init_state(messages=None):
    messages = messages or []
    return {
        "messages": messages,
        "n_calls": 0,
        "step_limit": step_limit,
        "n_errors": 0,
        "max_errors": max_errors,
        "cwd": cwd,
        "n_saved": len(messages),
        "session_path": None,
    }

def add_message(state, role, content):
    state["messages"].append({"role": role, "content": content})