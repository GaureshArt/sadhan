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

    start = (249, 115, 22)    
    end = (250, 204, 21)      

    max_width = max(len(line) for line in art)

    for line in art:
        for i, char in enumerate(line):
            if char == " ":
                text.append(" ")
                continue 

            t = i / max_width

            r = int(start[0] + (end[0] - start[0]) * t)
            g = int(start[1] + (end[1] - start[1]) * t)
            b = int(start[2] + (end[2] - start[2]) * t)

            text.append(char, style=f"bold #{r:02x}{g:02x}{b:02x}")

        text.append("\n")

    return text