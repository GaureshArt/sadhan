import asyncio
import os
import re
import signal
import time
from uuid import uuid4

from .config import blocked_patterns, cwd, max_output_bytes, timeout

shell = None


def strip_heredocs(command):
    lines = command.split("\n")
    out = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        match = re.search(r"<<\s*-?\s*'?([A-Za-z_][A-Za-z0-9_]*)'?", lines[i])
        if i < len(lines) - 1 and match:
            delim = match.group(1)
            i += 1
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
        i += 1
    return "\n".join(out)


def is_blocked(command):
    return any(re.search(pattern, strip_heredocs(command)) for pattern in blocked_patterns)


def killpg(proc):
    if proc is not None and proc.returncode is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


async def spawn():
    return await asyncio.create_subprocess_exec(
        "bash",
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )


async def run_bash_command(command):
    global shell

    if is_blocked(command):
        return {"returncode": -1, "output": "[BLOCKED COMMAND]"}

    if shell is None or shell.returncode is not None:
        shell = await spawn()

    token = uuid4().hex[:8]
    marker = f"__SADHAN_DONE_{token}_"
    payload = f"{command}\necho {marker}$?\n"

    try:
        shell.stdin.write(payload.encode("utf-8"))
        await shell.stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        shell = await spawn()
        shell.stdin.write(payload.encode("utf-8"))
        await shell.stdin.drain()

    chunks = []
    total = 0
    started = time.monotonic()

    try:
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise asyncio.TimeoutError

            line = await asyncio.wait_for(shell.stdout.readline(), timeout=remaining)
            if not line:
                shell = None
                return {"returncode": -1, "output": "".join(chunks) + "\n[SHELL DIED]"}

            text = line.decode("utf-8", errors="replace")
            stripped = text.rstrip("\n")
            match = re.search(re.escape(marker) + r"(-?\d+)$", stripped)
            if match:
                pre = stripped[: match.start()]
                if pre:
                    chunks.append(pre + "\n")
                return {"returncode": int(match.group(1)), "output": "".join(chunks)}

            total += len(text)
            if total > max_output_bytes:
                killpg(shell)
                shell = None
                return {"returncode": -1, "output": "".join(chunks) + "\n[OUTPUT LIMIT EXCEEDED]"}
            chunks.append(text)

    except asyncio.TimeoutError:
        killpg(shell)
        shell = None
        return {"returncode": -1, "output": "".join(chunks) + "\n[COMMAND TIMED OUT]"}
    except asyncio.CancelledError:
        killpg(shell)
        shell = None
        return {"returncode": -1, "output": "".join(chunks) + "\n[CANCELLED]"}