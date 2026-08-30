import os
import queue
import re
import signal
import subprocess
import threading
import time
from uuid import uuid4

from .config import blocked_patterns, cwd, max_output_bytes, timeout
from .control import is_cancelled


def _killpg():
    if shell is not None and shell.poll() is None:
        try:
            os.killpg(os.getpgid(shell.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _strip_heredocs(command):
    lines = command.split("\n")
    out = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        m = re.search(r"<<\s*-?\s*'?([A-Za-z_][A-Za-z0-9_]*)'?", lines[i])
        if i < len(lines) - 1 and m:
            delim = m.group(1)
            i += 1
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
        i += 1
    return "\n".join(out)


def is_blocked(command):
    return any(re.search(pattern, _strip_heredocs(command)) for pattern in blocked_patterns)


def _pump(pipe, q):
    for line in pipe:
        q.put(line)
    q.put(None)


def spawn():
    global _q
    proc = subprocess.Popen(
        ["bash"],
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _q = queue.Queue()
    threading.Thread(target=_pump, args=(proc.stdout, _q), daemon=True).start()
    return proc


def send(payload):
    try:
        shell.stdin.write(payload.encode("utf-8"))
        shell.stdin.flush()
    except (BrokenPipeError, OSError):
        return False
    return True


shell = None
_q = None


def run_bash_command(command):
    if is_blocked(command):
        return {"returncode": -1, "output": "[BLOCKED COMMAND]"}

    global shell
    if shell is None or shell.poll() is not None:
        shell = spawn()

    token = uuid4().hex[:8]
    marker = f"__SADHAN_DONE_{token}_"
    payload = f"{command}\necho {marker}$?\n"
    if not send(payload):
        shell.kill()
        shell = spawn()
        send(payload)

    chunks = []
    total = 0
    started = time.monotonic()
    while True:
        if is_cancelled():
            _killpg()
            shell = None
            return {"returncode": -1, "output": "".join(chunks) + "\n[CANCELLED]"}
        try:
            data = _q.get(timeout=0.2)
        except queue.Empty:
            if time.monotonic() - started > timeout:
                _killpg()
                shell = None
                return {"returncode": -1, "output": "".join(chunks) + "\n[COMMAND TIMED OUT]"}
            continue
        if data is None:
            shell = None
            return {"returncode": -1, "output": "".join(chunks) + "\n[SHELL DIED]"}
        buf = data
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("utf-8", errors="replace")
            m = re.search(re.escape(marker) + r"(-?\d+)$", line)
            if m:
                pre = line[: m.start()]
                if pre:
                    chunks.append(pre + "\n")
                return {"returncode": int(m.group(1)), "output": "".join(chunks)}
            total += len(line)
            if total > max_output_bytes:
                _killpg()
                shell = None
                return {"returncode": -1, "output": "".join(chunks) + "\n[OUTPUT LIMIT EXCEEDED]"}
            chunks.append(line + "\n")
