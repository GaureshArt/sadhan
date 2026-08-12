

from state import add_message, init_state
from bash import run_bash_command
from prompt import system_propmt
from llm_call import llm_call


def step(state):
    response = llm_call(state)
    if response['action'] != 'echo TASK_COMPLETE':
        action_response = run_bash_command(response['action'])
        add_message(state,role='user',content=f"Bash Result \n returncode:{action_response['returncode']} \n output:{action_response['output']}")
    return response


def agent():
    state = init_state()
    add_message(state,role='system',content=system_propmt)
    add_message(state,role='user',content=input("Enter your task: "))
    while True:
        try:
            if state['n_calls'] >= state['step_limit']:
                break
            if state['n_errors'] >= state['max_errors']:
                break
            output = step(state)
            print(state['messages'][-1])
            if output['action'] == 'echo TASK_COMPLETE':
                print("Task  complete")
                break
        except Exception as e:
            state['n_errors']+=1
            add_message(state,role='user',content=f"Agent error : {e}")
        finally:
            state['n_calls']+=1    




if __name__ == "__main__":
    agent()