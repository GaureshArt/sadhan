import json

from pydantic import BaseModel, Field, ValidationError

from .bash import run_bash_command


class RunBash(BaseModel):
    """A single bash command to execute in the agent's persistent shell."""

    command: str = Field(
        ...,
        description=(
            "A single bash command to run in the persistent shell. The working "
            "directory and environment (cd, exports, activated venvs) persist "
            "between calls. Chain dependent steps with &&."
        ),
    )
    reason: str = Field(
        "",
        description=(
            "One short sentence explaining why you are running this command, "
            "e.g. 'list the directory to see what's here'."
        ),
    )


BASH_TOOL = "run_bash"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": BASH_TOOL,
            "description": (
                "Execute a single bash command in the project's persistent shell. "
                "Use this tool for every action: exploring files, running commands "
                "or tests, creating/editing files, installing dependencies. When the "
                "task is fully done and verified, stop calling tools and reply with a "
                "short final message instead."
            ),
            "parameters": RunBash.model_json_schema(),
        },
    }
]


def parse_tool_arguments(arguments: str) -> dict:
    arguments = (arguments or "").strip()
    try:
        parsed = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError as e:
        raise ValueError(f"tool arguments are not valid JSON: {e.msg}") from e
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be a JSON object")
    return parsed


def parse_command(arguments: str) -> str:
    parsed = parse_tool_arguments(arguments)
    try:
        command = RunBash.model_validate(parsed).command
    except ValidationError as e:
        raise ValueError(f"invalid tool arguments: {e.errors()}") from e
    if not command.strip():
        raise ValueError("command must not be empty")
    return command


async def run_bash_tool(arguments: str) -> dict:
    command = parse_command(arguments)
    return await run_bash_command(command)