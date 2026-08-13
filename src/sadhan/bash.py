import subprocess
from subprocess import STDOUT
from config import cwd

def run_bash_command(command):
    result = subprocess.run(
        command,
        cwd=cwd,
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