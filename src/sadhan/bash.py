import subprocess
from subprocess import STDOUT
from config import cwd,timeout

def run_bash_command(command):
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
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
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "output": "[COMMAND TIMED OUT]"}