import logging

from .base import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    async def close(self) -> None:
        for tool in self._tools.values():
            try:
                await tool.close()
            except Exception:
                logger.exception("Closing tool %s failed", tool.name)
