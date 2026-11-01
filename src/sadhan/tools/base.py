from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from ..messages import ToolUseBlock

Hook = Callable[[ToolUseBlock], Awaitable[str | None]]


class Tool:
    name: str
    description: str
    params: type[BaseModel]

    def to_schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.params.model_json_schema()}}

    async def run(self, args: BaseModel) -> str:
        raise NotImplementedError

    async def close(self) -> None:
        """Release resources (processes, connections). Called once at shutdown."""
