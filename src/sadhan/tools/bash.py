from pydantic import BaseModel, Field

from .shell import Shell
from .base import Tool


class BashParams(BaseModel):
    command: str = Field(description="The shell command to run")


class BashTool(Tool):
    name = "bash"
    description = (
        "Run a shell command in the project directory and return its output. "
        "Each call starts a fresh shell, so `cd` and exported variables do not "
        "carry over: chain commands with && instead. Non-zero exit codes are "
        "shown after the output."
    )
    params = BashParams

    def __init__(self, shell: Shell, timeout: float) -> None:
        self.shell = shell
        self.timeout = timeout

    async def run(self, args: BashParams) -> str:
        output, code = await self.shell.run(args.command, self.timeout)
        if code != 0:
            output += f"\n[exit code: {code}]"
        return output