import subprocess
from subprocess import STDOUT


def run_bash_command(command):
    result = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=STDOUT,
        text=True,
        encoding="utf-8",
    )

    return {
        "returncode": result.returncode,
        "output": result.stdout,
    }


if __name__ == "__main__":
    result = run_bash_command("cat .gitignore")
    print(result)