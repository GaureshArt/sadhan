import importlib.util
import logging
import sys
from pathlib import Path

from .config import Config
from .event import EventBus
from .tools.base import Hook, Tool
from .tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class PluginHost:
    """What a plugin's register(host) receives: its way to extend Sadhan."""

    def __init__(self, config: Config, bus: EventBus) -> None:
        self.config = config
        self.bus = bus
        self.tools = ToolRegistry()
        self.before_tool_hooks: list[Hook] = []

    def add_tool(self, tool: Tool) -> None:
        self.tools.add(tool)

    def before_tool(self, hook: Hook) -> Hook:
        self.before_tool_hooks.append(hook)
        return hook


def load_plugins(directory: Path, host: PluginHost) -> None:
    """Import every .py file in directory and call its register(host)."""
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.py")):
        name = f"sadhan_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            module.register(host)
        except Exception:
            sys.modules.pop(name, None)
            logger.exception("Plugin %s failed to load", path.name)
