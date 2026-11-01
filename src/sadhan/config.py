from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

system_prompt: str = (
    "You are sadhan, a coding agent working inside the current project directory.\n"
    "Use the available tools to complete the user's task. Run one command per tool call, "
    "read its output, then decide the next step.\n"
    "Never create, modify, or delete anything outside the working directory.\n"
    "When the task is complete, reply with a short summary and do not call any tool."
)


class Config(BaseModel):
    """Fixed configuration of agent"""

    model_config = ConfigDict(frozen=True, extra="forbid")
    model: str | None = None
    api_base: str | None = None
    max_steps: int = Field(100, gt=0)
    max_consecutive_errors: int = Field(5, gt=0)
    working_dir: Path = Field(default_factory=Path.cwd)
    command_timeout: float = Field(120, gt=0)
    max_output_chars: int = Field(10_000, gt=1000)
    system_prompt: str | None = system_prompt
