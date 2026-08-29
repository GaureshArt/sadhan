from .agent import agent
def main():
    while True:
        task = input("What do you want to do? (or 'exit' to quit)\n")
        if task.strip().lower() in ("exit",""):
            break
        result = agent(task)
        print(f"Task finished: {result}")
if __name__ == "__main__":
    main()
