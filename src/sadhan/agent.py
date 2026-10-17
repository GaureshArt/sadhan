from .config import Config
from .messages import Message, TextBlock, ToolResultBlock
from .tools.base import Tool
from .event import ErrorOccurred, EventBus, RunFinished, StepStarted, ToolFinished, ToolStarted, TextDelta
from .provider import Provider
from .state import State
class Agent:
    def __init__(self,provider:Provider,config:Config,tools:list[Tool],bus:EventBus | None = None):
        self.config = config
        self.bus = bus if bus is not None else EventBus()
        self.provider = provider
        self.state = State()
        self._tools = {t.name:t for t in tools}
    async def _step(self):
        reply = await self.provider.chat(messages=self.state.messages,tools=[t.to_schema() for t in self._tools.values()],system_prompt=self.config.system_prompt,on_text_delta=lambda delta:self.bus.emit(TextDelta(delta=delta)))
        self.state.add(reply)

        if not reply.tool_uses:
            return True
        results = []
        for call in reply.tool_uses:
            self.bus.emit(ToolStarted(call=call))

            tool = self._tools.get(call.name)
            if tool is None:
                result = ToolResultBlock(tool_use_id=call.id,content=f"Unknown tool: {call.name}",is_error=True)
                self.state.record_error()
            else:
                try:
                    args = tool.params.model_validate(call.input)
                    output = await tool.run(args)
                    result = ToolResultBlock(tool_use_id=call.id,content=output)
                except Exception as exc:
                    result = ToolResultBlock(tool_use_id=call.id, content=str(exc),is_error=True)
                    self.state.record_error()
            self.bus.emit(ToolFinished(call=call,result=result))
            results.append(result)

        self.state.add(Message(role='user',content=results))
        return False

        


            
          


    async def run(self,user_query:str):
        self.state.add(Message.user(user_query))
        self.state.status = 'running'
        while True:
            self.state.step+=1
            self.bus.emit(StepStarted(step=self.state.step))
            if self.state.step > self.config.max_steps:
                self.state.status = 'error'
                
                self.bus.emit(RunFinished(status='error'))
                return None
            try:
                done = await self._step()
            except Exception as exc:
                self.state.record_error()
                self.bus.emit(ErrorOccurred(error=str(exc)))
                if self.state.consecutive_errors >= self.config.max_consecutive_errors:
                    self.state.status = 'error'
                    self.bus.emit(RunFinished(status='error'))
                    return None
                continue
            self.state.reset_error()
            if done:
                self.state.status = 'done'
                final = self.state.last_assistant
                self.bus.emit(RunFinished(status='done',message=final))
                return final


       