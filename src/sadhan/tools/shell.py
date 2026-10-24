import asyncio
import os
import re
import shlex
import signal
from asyncio.subprocess import PIPE, STDOUT, Process
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

MAX_OUTPUT_BYTES = 1_000_000
SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _env() -> dict[str, str]:
    """Environment minus likely secrets and BASH_ENV (a startup-file hook)."""
    return {k: v for k, v in os.environ.items() if k != "BASH_ENV" and not any(w in k.upper() for w in SECRET_WORDS)}


class PersistentShell:
    """One long-lived bash: cd, variables and functions carry over between commands."""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir
        self._proc: Process | None = None
        self._lock = asyncio.Lock()

    async def run(self, command: str, timeout: float) -> tuple[str, int]:
        async with self._lock:
            marker = uuid4().hex
            proc = await self._start()
            done = re.compile(rf"\n{marker}:(\d+)\n".encode())
            script = f"eval {shlex.quote(command)} </dev/null\nprintf '\\n{marker}:%s\\n' \"$?\"\n"
            try:
                async with asyncio.timeout(timeout):
                    proc.stdin.write(script.encode())
                    buffer = b""
                    while not (found := done.search(buffer)):
                        chunk = await proc.stdout.read(65536)
                        if not chunk:
                            self._proc = None
                            text = buffer.decode(errors="replace") + "\n[shell exited]"
                            return text, await proc.wait()
                        buffer += chunk
                        if len(buffer) > MAX_OUTPUT_BYTES:
                            raise RuntimeError(f"Output exceeded {MAX_OUTPUT_BYTES} bytes; filter it with head, tail or grep.")
                    return buffer[: found.start()].decode(errors="replace"), int(found[1])
            except BaseException as exc:
                await self.close()
                if isinstance(exc, TimeoutError):
                    raise TimeoutError(f"Timed out after {timeout}s; shell restarted, cd and variables were lost.") from None
                raise

    async def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc:
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()

    async def _start(self) -> Process:
        if self._proc is None or self._proc.returncode is not None:
            self._proc = await asyncio.create_subprocess_exec(
                "bash",
                cwd=self.working_dir,
                env=_env(),
                stdin=PIPE,
                stdout=PIPE,
                stderr=STDOUT,
                start_new_session=True,
            )
        return self._proc
