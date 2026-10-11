import asyncio
import os
import signal


class Shell:
    def __init__(self, working_path):
        self.working_path = working_path

    async def run(self, cmd, timeout):
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            cmd,
            cwd=self.working_path,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )

        try:
            output, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
            raise TimeoutError(f"Command timed out after {timeout} seconds") from None
        return output.decode(errors="replace"), proc.returncode
