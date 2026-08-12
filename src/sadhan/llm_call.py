from ollama import chat
from config import model
from state import add_message
from parser import parser
def llm_call(state:dict):
    response = chat(
        model=model,
        messages=state['messages'],
        think=False
    )
    content = response['message']['content']
    add_message(state,role='assistant',content=content)
    print(content)
    return parser(content)


# if __name__ == "__main__":
#     llm_call({'messages':[{'role':'user','content':'Hello '}]})