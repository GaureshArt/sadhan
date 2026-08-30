model = 'qwen3.5:4b'
step_limit = 30
max_errors = 4
cwd = r"/home/gaureshart/Codebases/AI-Engineering/Projects/testing_sadhan"
timeout = 60
max_output_bytes = 100_000

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