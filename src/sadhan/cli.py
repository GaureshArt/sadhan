from .event import (
    ErrorOccurred,
    Event,
    RunFinished,
    StepStarted,
    TextDelta,
    ToolFinished,
    ToolStarted,
)


class CliRenderer:
    def __init__(self) -> None:
        self._mid_line = False
    def handle(self, event: Event) -> None:
        if not isinstance(event, TextDelta) and self._mid_line:
            print()                      
            self._mid_line = False

        if isinstance(event, TextDelta):
            print(event.delta, end="", flush=True)
            self._mid_line = True
        elif isinstance(event, ToolStarted):
            print(f"Tool Invoked: {event.call.name}")
        elif isinstance(event, ToolFinished):
            if event.result.is_error:
                print(f"Tool failed: {event.result.content}")
            else:
                print(f"Tool Result: {event.result.content}")
        elif isinstance(event, StepStarted):
            print(f"Step {event.step} started.")
        elif isinstance(event, RunFinished):
            if event.message is not None:
                print(f"Assistant: {event.message.text}")
            if event.status != "done":
                print(f"Run {event.status}.")
        elif isinstance(event, ErrorOccurred):
            print(f"Error: {event.error}")
