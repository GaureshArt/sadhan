import os

def resolve_workdir(arg=None):
    if arg:
        path = os.path.abspath(os.path.expanduser(arg))
        if not os.path.isdir(path):
            raise ValueError(f"{arg!r} is not a directory")
        return path
    return os.getcwd()


model = 'qwen3.5:4b'
step_limit = 30
max_errors = 4
cwd = os.getcwd()
timeout = 60
max_output_bytes = 100_000
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
fold_lines = 8
collapse_output = True

blocked_patterns = [
    r"\bsudo\b", r"\bsu\s", r"\bshutdown\b", r"\breboot\b", r"\bpoweroff\b",
    r":\(\)\s*\{.*\}\s*;\s*:",
    r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)",
    r"\bmkfs", r"\bdd\s+.*of=/dev/",
    r"\b(vim|vi|nano|emacs|top|htop)\b",
    r"\bgit\s+(push\s+--force|push\s+-f|reset\s+--hard|clean\s+-fd)",
    r"\bchmod\s+-R\s+777\s+/",
]