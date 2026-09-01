import json
import re
import time
from datetime import datetime
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


def meta_path(session_path):
    return session_path.with_suffix(".meta.json")


def read_meta(session_path):
    p = meta_path(session_path)
    if p.exists():
        return json.loads(p.read_text())
    return {"name": None}


def write_meta(session_path, name):
    meta_path(session_path).write_text(json.dumps({"name": name}))


def parse_timestamp(session_path):
    return datetime.strptime(session_path.stem, "%Y%m%d_%H%M%S")


def human_timestamp(session_path):
    dt = parse_timestamp(session_path)
    return dt.strftime("%b %d, %Y · %I:%M %p")


def session_label(session_path):
    meta = read_meta(session_path)
    when = human_timestamp(session_path)
    if meta.get("name"):
        return f"{meta['name']}  —  {when}"
    return when