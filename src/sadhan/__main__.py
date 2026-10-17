
import asyncio
from pathlib import Path

from .agent import Agent
from .cli import CliRenderer
from .config import Config
from .event import EventBus
from .provider import LiteLLMProvider
from .tools.bash import BashTool
from .tools.shell import Shell

# qwen3.5:4b on Ollama. The `ollama_chat/` prefix is what enables tool calling.
MODEL = "ollama_chat/qwen3.5:4b"
PROMPT = "sadhan> "


def build_agent(workdir: Path) -> Agent:
    config = Config(model=MODEL, working_dir=workdir)

    bus = EventBus()
    bus.subscribe(CliRenderer().handle)          # renderer <- events

    shell = Shell(config.working_dir)
    tools = [BashTool(shell, config.command_timeout)]
    provider = LiteLLMProvider(model=config.model, api_base=config.api_base)
    return Agent(provider, config, tools, bus)


async def repl() -> None:
    agent = build_agent(Path.cwd())

    while True:
        try:
            query = await asyncio.to_thread(input, PROMPT)
        except (EOFError, KeyboardInterrupt):
            print()
            return

        query = query.strip()
        if not query:
            continue

        # fresh step/error budget per query; conversation history is kept
        agent.state.step = 0
        agent.state.consecutive_errors = 0

        await agent.run(query)


def main() -> None:
    try:
        asyncio.run(repl())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()