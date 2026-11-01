import re

_HARMFUL = (
    ("privilege escalation", re.compile(r"\b(sudo|doas)\b|\bsu\s+\w")),
    ("recursive force delete", re.compile(r"\brm\b[^;\n]*\s-[a-zA-Z]*[rfRF][a-zA-Z]*[rfRF]")),
    ("fork bomb", re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;?\s*:")),
    ("shutdown / reboot", re.compile(r"\b(shutdown|reboot|poweroff|halt)\b|\binit\s+[06]\b|\bsystemctl\s+(reboot|poweroff|halt)\b")),
    ("disk destroy", re.compile(r"\bmkfs(\.\w+)?\b|\bwipefs\b|\bdd\b[^\n]*\bof=/dev/")),
    ("piped remote execution", re.compile(r"\b(curl|wget)\b[^\n|;&]*\|\s*\S*(ba|z|k)?sh\b")),
)

_COLLAPSE_SPACES = re.compile(r"\s+")


def register(host):
    """The hook contract: sadhan calls register(host) once at startup.
    The hook's shape is fixed by the harness: async fn(ToolUseBlock) -> str | None."""

    patterns = _HARMFUL

    async def bash_safety(call):
        if call.name != "bash":
            return None

        cmd = _COLLAPSE_SPACES.sub(" ", call.input.get("command", ""))

        for name, pattern in patterns:
            if pattern.search(cmd):
                return f"policy banned: {name} — rewrite the command without it"
        return None

    host.before_tool(bash_safety)
