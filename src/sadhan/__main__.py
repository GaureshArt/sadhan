import argparse
import asyncio
from contextlib import suppress
from pathlib import Path

from .agent import Agent
from .cli import CliRenderer
from .config import Config
from .event import EventBus
from .plugins import PluginHost, load_plugins
from .provider import LiteLLMProvider
from .tools.bash import BashTool

MODEL = "ollama_chat/qwen3.5:4b"
PROMPT = "sadhan> "


async def repl(agent) -> None:

    while True:
        try:
            query = await asyncio.to_thread(input, PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            return

        query = query.strip()
        if not query:
            continue

        agent.state.step = 0
        agent.state.consecutive_errors = 0

        await agent.run(query)


async def amain(model: str, api_base: str | None, workdir: Path) -> None:
    config = Config(model=model, api_base=api_base, working_dir=workdir)
    bus = EventBus()
    host = PluginHost(config=config, bus=bus)
    BashTool.register(host)
    load_plugins(Path.home() / ".sadhan" / "plugins", host)
    load_plugins(workdir / ".sadhan" / "plugins", host)
    bus.subscribe(CliRenderer().handle)
    agent = Agent(provider=LiteLLMProvider(config.model, config.api_base), config=config, tools=host.tools, bus=bus, hooks=host.before_tool_hooks)
    try:
        await repl(agent)
    finally:
        await host.tools.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sadhan")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--api-base")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if not args.cwd.is_dir():
        parser.error(f"--cwd: {args.cwd} is not a directory")
    with suppress(KeyboardInterrupt):
        asyncio.run(amain(args.model, args.api_base, args.cwd.resolve()))


if __name__ == "__main__":
    main()
