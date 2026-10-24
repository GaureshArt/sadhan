import argparse
import asyncio
from contextlib import suppress
from pathlib import Path

from .agent import Agent
from .cli import CliRenderer
from .config import Config
from .event import EventBus
from .provider import LiteLLMProvider
from .tools.bash import BashTool
from .tools.shell import PersistentShell

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
    bus.subscribe(CliRenderer().handle)
    shell = PersistentShell(config.working_dir)
    agent = Agent(
        LiteLLMProvider(config.model, config.api_base),
        config,
        [BashTool(shell, config.command_timeout)],
        bus,
    )
    try:
        await repl(agent)
    finally:
        await shell.close()


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
