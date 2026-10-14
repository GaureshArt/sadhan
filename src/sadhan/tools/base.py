from pydantic import BaseModel


class Tool:
    name: str
    description: str
    params: type[BaseModel]

    def to_schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.params.model_json_schema()}}

    async def run(self, args: BaseModel) -> str:
        raise NotImplementedError
