from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


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
    system_prompt: str | None = None
