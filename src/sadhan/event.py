import logging
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .messages import Message, ToolResultBlock, ToolUseBlock

logger = logging.getLogger(__name__)


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    agent_id: str = "main"


class StepStarted(Event):
    type: Literal["step_started"] = "step_started"
    step: int = Field(ge=0)


class ToolStarted(Event):
    type: Literal["tool_started"] = "tool_started"
    call: ToolUseBlock


class ToolFinished(Event):
    type: Literal["tool_finished"] = "tool_finished"
    call: ToolUseBlock
    result: ToolResultBlock


class RunFinished(Event):
    type: Literal["run_finished"] = "run_finished"
    status: Literal["done", "error", "cancelled"]
    message: Message | None = None


class ErrorOccurred(Event):
    type: Literal["error_occurred"] = "error_occurred"
    error: str = Field(..., min_length=1)


class TextDelta(Event):
    type: Literal["text_delta"] = "text_delta"
    delta: str


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self.handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        self.handlers.append(handler)

        def unsubscribe() -> None:
            if handler in self.handlers:
                self.handlers.remove(handler)

        return unsubscribe

    def emit(self, event: Event) -> None:
        for handler in list(self.handlers):
            try:
                handler(event)
            except Exception:
                logger.exception("Event handler failed")
