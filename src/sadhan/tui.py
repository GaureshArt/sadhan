import pyfiglet
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Input, RichLog, Static

from .agent import agent
from .bash import run_bash_command
from .config import model
from . import control as control_mod

GRADIENT = ["#00e5ff", "#38bdf8", "#818cf8", "#c084fc", "#e879f9"]

MODES = {
    "build": {
        "border": "#38bdf8",
        "placeholder": "Describe a task...  (Ctrl+B bash mode)",
        "label": "BUILD",
    },
    "bash": {
        "border": "#f472b6",
        "placeholder": "$ shell command runs directly  (Ctrl+B build mode)",
        "label": "BASH",
    },
}


def render_banner() -> Text:
    art = pyfiglet.figlet_format("SADHAN", font="broadway").splitlines()
    out = Text(justify="center")
    n = len(art)
    for i, line in enumerate(art):
        idx = round(i * (len(GRADIENT) - 1) / max(n - 1, 1))
        out.append(line + "\n", style=GRADIENT[idx])
    return out


class SadhanApp(App):
    TITLE = "sadhan"
    AUTO_FOCUS = "#prompt"

    CSS = """
    #banner {
        height: auto;
        
        
        padding: 1 0 1 0;
    }
    #log {
        height: 1fr;
        padding: 0 1;
    }
    #bottom {
        height: auto;
    }
    #status {
        height: 1;
        padding: 0 2;
        background: $panel;
        color: $text-muted;
    }
    #prompt {
        margin: 1 0 1 0;
    }
    """

    BINDINGS = [
        ("ctrl+b", "toggle_mode", "Switch mode"),
        ("escape", "cancel_task", "Cancel task"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+y", "copy_transcript", "Copy log"),
        ("ctrl+g", "copy_output", "Copy last output"),
    ]

    def __init__(self):
        super().__init__()
        self.mode = "build"
        self.steps = 0
        self.busy = False
        self.started = False
        self._run_id = 0
        self._reasoning = Text()
        self._reasoning_words = 0
        self._transcript: list[str] = []
        self._last_output = ""

    def compose(self) -> ComposeResult:
        yield Static(render_banner(), id="banner")
        yield RichLog(id="log", highlight=True, wrap=True)
        with Vertical(id="bottom"):
            yield Static(self.status_line(), id="status")
            yield Input(placeholder=MODES["build"]["placeholder"], id="prompt")
        yield Footer()

    @property
    def log_widget(self) -> RichLog:
        return self.query_one("#log", RichLog)

    @property
    def prompt(self) -> Input:
        return self.query_one("#prompt", Input)

    def status_line(self) -> str:
        m = MODES[self.mode]
        return f" {m['label']}  ·  {model}  ·  steps {self.steps}  ·  Esc cancel · Ctrl+B switch · Ctrl+Q quit"

    def refresh_status(self) -> None:
        self.query_one("#status", Static).update(self.status_line())

    def apply_mode_style(self) -> None:
        m = MODES[self.mode]
        self.prompt.placeholder = m["placeholder"]
        self.prompt.styles.border = ("round", m["border"])
        self.refresh_status()

    def action_toggle_mode(self) -> None:
        self.mode = "bash" if self.mode == "build" else "build"
        self.apply_mode_style()

    def action_cancel_task(self) -> None:
        if self.busy:
            control_mod.cancelled.set()
            self.workers.cancel_group(self, "task")
            self._flush_reasoning()
            self.busy = False
            self.prompt.disabled = False
            self.prompt.focus()
            self.write_styled("cancel requested…", "yellow")

    def write_styled(self, text: str, style: str = "") -> None:
        self.log_widget.write(Text(text, style=style))
        self._transcript.append(text)

    def _notify(self, text: str, style: str = "") -> None:
        self.log_widget.write(Text(text, style=style))

    def _flush_reasoning(self) -> None:
        if self._reasoning:
            self._transcript.append(self._reasoning.plain)
            self.log_widget.write(self._reasoning)
            self._reasoning = Text()
            self._reasoning_words = 0

    def handle_event(self, event: dict) -> None:
        if "_run" in event and event["_run"] != self._run_id:
            return
        t = event["type"]
        if t == "reasoning_token":
            self._reasoning.append(event["text"])
            self._reasoning_words += len(event["text"].split())
            if "\n" in event["text"] or self._reasoning_words >= 12:
                self._flush_reasoning()
        elif t == "action":
            self._flush_reasoning()
            self.write_styled(f"$ {event['command']}", "bold cyan")
        elif t == "result":
            self._flush_reasoning()
            self.steps += 1
            ok = event["returncode"] == 0
            self.write_styled(
                f"$ exit={event['returncode']}",
                "green" if ok else "red",
            )
            self.write_styled(event["output"].rstrip("\n"), "dim")
            self._last_output = event["output"]
            self.refresh_status()
        elif t == "error":
            self._flush_reasoning()
            self.write_styled(f"agent error: {event['message']}", "bold red")
        elif t == "status":
            self._flush_reasoning()
            if event.get("status") == "complete":
                self.write_styled("✓ task complete", "bold green")
            elif event.get("status") == "stopped":
                self.write_styled(f"✗ stopped: {event['reason']}", "bold yellow")
            elif event.get("status") == "cancelled":
                self.write_styled("✗ cancelled", "bold yellow")
        elif t == "done":
            self._flush_reasoning()
            self.busy = False
            self.prompt.disabled = False
            self.prompt.focus()
            self.write_styled("─" * 40, "dim")
        elif t == "user":
            self._flush_reasoning()
            self.write_styled(f"\n❯ {event['text']}\n", "bold cyan")

    def start_worker(self, fn) -> None:
        self.busy = True
        self.prompt.disabled = True
        control_mod.new_run()
        self._run_id += 1
        rid = self._run_id

        def wrapped():
            try:
                fn(lambda e: self.call_from_thread(self.handle_event, {**e, "_run": rid}))
            except Exception as e:
                try:
                    self.call_from_thread(self.handle_event, {"type": "error", "message": str(e), "_run": rid})
                except Exception:
                    pass
            finally:
                try:
                    self.call_from_thread(self.handle_event, {"type": "done", "_run": rid})
                except Exception:
                    pass

        self.run_worker(wrapped, thread=True, group="task", exclusive=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.prompt.clear()
        if not text:
            return
        if self.busy:
            self.write_styled("a task is still running (Esc to cancel)", "yellow")
            return
        if not self.started:
            self.query_one("#banner", Static).remove()
            self.started = True
        self.handle_event({"type": "user", "text": text})
        if self.mode == "build":

            def run(emit):
                agent(text, emit=emit)

            self.start_worker(run)
        else:

            def run(emit):
                result = run_bash_command(text)
                emit({
                    "type": "result",
                    "returncode": result["returncode"],
                    "output": result["output"],
                })

            self.start_worker(run)

    def _copy(self, content: str, what: str) -> None:
        if not content:
            self._notify(f"no {what} to copy", "yellow")
            return
        try:
            self.copy_to_clipboard(content)
        except Exception as e:
            self._notify(f"copy failed: {e}", "red")
            return
        n = len(content.splitlines())
        self._notify(f"copied {what} ({n} {'line' if n == 1 else 'lines'}) to clipboard", "bold green")

    def action_copy_transcript(self) -> None:
        content = "\n".join(self._transcript).strip("\n")
        self._copy(content, "log")

    def action_copy_output(self) -> None:
        self._copy(self._last_output.rstrip("\n"), "last output")


def main():
    SadhanApp().run()


if __name__ == "__main__":
    main()
