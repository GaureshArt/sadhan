from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .messages import Message

SCHEMA_VERSION = 1


class State(BaseModel):
    """Data of one agent run."""

    model_config = ConfigDict(validate_assignment=True)
    schema_version: int = SCHEMA_VERSION
    messages: list[Message] = Field(default_factory=list)
    step: int = 0
    consecutive_errors: int = 0
    status: Literal["idle", "running", "done", "error", "cancelled"] = "idle"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "State":
        """Load a saved state; raises ValueError if it comes from a newer schema."""
        version = data.get("schema_version", 1)
        if version > SCHEMA_VERSION:
            raise ValueError(f"Session was saved by a newer Sadhan schema version:{version}")
        return cls.model_validate(data)

    @property
    def last_assistant(self) -> Message | None:
        """Most recent assistant message, or None if there isn't one yet."""
        for message in reversed(self.messages):
            if message.role == "assistant":
                return message

        return None

    def add(self, message: Message) -> None:
        self.messages.append(message)

    def record_error(self) -> None:
        self.consecutive_errors += 1

    def reset_error(self) -> None:
        self.consecutive_errors = 0
