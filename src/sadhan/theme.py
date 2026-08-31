import pyfiglet
from rich.text import Text

BG = "#0c0d12"
BORDER = "#23252f"
BORDER_FOCUS = "#38bdf8"

USER = "#f5f5f5"
REASON = "#c9915a"

ACTION = "#f0abfc"        
ACTION_BG = "on #17181d"
ACTION_FG = "#e5e5e0"

OK = "#4ade80"
FAIL = "#f87171"
DIM = "#4b5563"

OUT_BG = "on #f4f4ef"
OUT_FG = "#111111"


def banner():
    art = pyfiglet.figlet_format("sadhan", font="block").splitlines()
    text = Text(justify="center")
    for line in art:
        text.append(line + "\n", style=f"bold {USER}")
    return text