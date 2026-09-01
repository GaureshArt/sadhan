import json
import re
import time
from pathlib import Path

from .config import cwd

SESSIONS_ROOT = Path.home() / ".sadhan" / "sessions"


def dir_slug():
    return re.sub(r"[^A-Za-z0-9]+", "_", str(Path(cwd).resolve())).strip("_")


def session_dir():
    d = SESSIONS_ROOT / dir_slug()
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_session_path():
    return session_dir() / f"{time.strftime('%Y%m%d_%H%M%S')}.jsonl"


def list_sessions():
    return sorted(session_dir().glob("*.jsonl"), reverse=True)


def flush_session(state):
    path = state["session_path"]
    if path is None:
        return
    new_messages = state["messages"][state["n_saved"]:]
    if not new_messages:
        return
    with open(path, "a", encoding="utf-8") as f:
        for m in new_messages:
            f.write(json.dumps(m) + "\n")
    state["n_saved"] = len(state["messages"])


def load_session(path):
    messages = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages