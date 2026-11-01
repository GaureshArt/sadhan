from .event import ErrorOccurred, EventBus, RunFinished, StepStarted, TextDelta, ToolFinished, ToolStarted
from .messages import Message, ToolResultBlock
from .state import State


class Agent:
    def __init__(self, *, provider, config, tools, hooks, bus=None):
        self.config = config
        self.bus = bus if bus is not None else EventBus()
        self.provider = provider
        self.state = State()
        self.tools = tools
        self.hooks = hooks
        self._is_step_tool_failed = False

    async def _step(self):
        reply = await self.provider.chat(
            messages=self.state.messages,
            tools=self.tools.schemas(),
            system_prompt=self.config.system_prompt,
            on_text_delta=lambda delta: self.bus.emit(TextDelta(delta=delta)),
        )
        self.state.add(reply)

        if not reply.tool_uses:
            return True
        results = []
        for call in reply.tool_uses:
            self.bus.emit(ToolStarted(call=call))

            tool = self.tools.get(call.name)
            if tool is None:
                result = ToolResultBlock(tool_use_id=call.id, content=f"Unknown tool: {call.name}", is_error=True)
                self._is_step_tool_failed = True
            else:
                try:
                    args = tool.params.model_validate(call.input)
                    for hook in self.hooks:
                        reason = await hook(call)
                        if reason is not None:
                            result = ToolResultBlock(tool_use_id=call.id, content=f"[BLOCKED] {reason}", is_error=True)
                            break
                    else:
                        output = await tool.run(args)
                        result = ToolResultBlock(tool_use_id=call.id, content=output)
                except Exception as exc:
                    result = ToolResultBlock(tool_use_id=call.id, content=str(exc), is_error=True)
                    self._is_step_tool_failed = True
            self.bus.emit(ToolFinished(call=call, result=result))
            results.append(result)

        self.state.add(Message(role="user", content=results))
        return False

    async def run(self, user_query: str):
        self.state.add(Message.user(user_query))
        self.state.status = "running"
        while True:
            self.state.step += 1
            self.bus.emit(StepStarted(step=self.state.step))
            if self.state.step > self.config.max_steps:
                self.state.status = "error"

                self.bus.emit(RunFinished(status="error"))
                return None
            try:
                done = await self._step()
                failed = self._is_step_tool_failed
                self._is_step_tool_failed = False
                if failed:
                    raise Exception("Tool Called Failed. Trying again.")
            except Exception as exc:
                self.state.record_error()
                self.bus.emit(ErrorOccurred(error=str(exc)))
                if self.state.consecutive_errors >= self.config.max_consecutive_errors:
                    self.state.status = "error"
                    self.bus.emit(RunFinished(status="error"))
                    return None
                continue
            else:
                self.state.reset_error()
            if done:
                self.state.status = "done"
                final = self.state.last_assistant
                self.bus.emit(RunFinished(status="done", message=final))
                return final
