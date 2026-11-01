from pydantic import BaseModel, Field

from ..plugins import PluginHost
from .base import Tool
from .shell import PersistentShell


class BashParams(BaseModel):
    command: str = Field(description="The shell command to run")


class BashTool(Tool):
    name = "bash"
    description = (
        "Run a shell command in the project directory and return its output. "
        "It is persistant shell. cd and exported variables persist between calls, and that a timeout restarts the shell and loses that state."
    )
    params = BashParams

    def __init__(self, shell: PersistentShell, timeout: float) -> None:
        self.shell = shell
        self.timeout = timeout

    async def run(self, args: BashParams) -> str:
        output, code = await self.shell.run(args.command, self.timeout)
        if code != 0:
            output += f"\n[exit code: {code}]"
        return output

    def register(host: PluginHost) -> None:
        shell = PersistentShell(host.config.working_dir)
        host.add_tool(BashTool(shell, host.config.command_timeout))
