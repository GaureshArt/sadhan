import asyncio

import pyfiglet
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Input, RichLog, Static

from .agent import agent
from .bash import run_bash_command
from .config import collapse_output, fold_lines, model
from .state import init_state

REASON = "#8b8bf5"
ACTION = "#38bdf8"
OK = "#4ade80"
FAIL = "#f87171"
OUT_BG = "on #16171d"

uid_counter = 0


def fold_mark(text, id):
    text.stylize(Style(meta={"fold": id}))
    return text


class Log(RichLog):
    def on_click(self, event):
        meta = event.style.meta if event.style else None
        if meta and "fold" in meta:
            self.app.on_fold(meta["fold"])
        event.stop()


class Block:
    def __init__(self, kind, body="", rend=None, rc=None, foldable=False, collapsed=False, live=False):
        global uid_counter
        uid_counter += 1
        self.id = uid_counter
        self.kind = kind
        self.body = body
        self.rend = rend if rend is not None else Text(body)
        self.rc = rc
        self.foldable = foldable
        self.collapsed = collapsed
        self.live = live

    def n_lines(self):
        return len(self.body.splitlines())

    def render(self):
        k = self.kind
        if k == "reasoning":
            if self.collapsed:
                return [fold_mark(Text("Reasoning", f"bold {REASON}"), self.id)]
            parts = [fold_mark(Text("Reasoning", f"bold {REASON}"), self.id), self.rend]
            if not self.live:
                parts.append(fold_mark(Text("collapse", f"dim {REASON}"), self.id))
            return parts
        if k == "action":
            if self.collapsed:
                return [fold_mark(Text("Action", f"bold {ACTION}"), self.id)]
            return [
                fold_mark(Text("Action", f"bold {ACTION}"), self.id),
                Text(f"$ {self.body}", f"bold {ACTION}"),
                fold_mark(Text("collapse", f"dim {ACTION}"), self.id),
            ]
        if k == "result":
            color = OK if self.rc == 0 else FAIL
            if not self.foldable:
                return [Text(f"exit={self.rc}", color), Text(self.body, f"dim {OUT_BG}")]
            if self.collapsed:
                return [fold_mark(Text(f"Output ({self.n_lines()} lines) exit={self.rc}", color), self.id)]
            return [
                fold_mark(Text(f"Output ({self.n_lines()} lines) exit={self.rc}", color), self.id),
                Text(self.body, f"dim {OUT_BG}"),
                fold_mark(Text("collapse", "dim"), self.id),
            ]
        return [self.rend]


MODES = {
    "build": {"border": "#38bdf8", "placeholder": "Describe a task...  (ctrl+b bash)", "label": "build"},
    "bash": {"border": "#f472b6", "placeholder": "$ shell command  (ctrl+b build)", "label": "bash"},
}


def render_banner():
    art = pyfiglet.figlet_format("sadhan", font="small").splitlines()
    text = Text(justify="center")
    for line in art:
        text.append(line + "\n", style="bold #38bdf8")
    return text


class SadhanApp(App):
    TITLE = "sadhan"
    AUTO_FOCUS = "#prompt"

    CSS = """
    Screen { background: $surface; }
    #banner { height: auto; padding: 1 0; }
    #log {
        height: 1fr;
        padding: 1 2;
        margin: 1 1 0 1;
        border: round #2a2d3a;
    }
    #bottom { height: auto; padding: 0 1 1 1; }
    #status { height: 1; padding: 0 2; color: $text-muted; }
    #prompt { border: round #2a2d3a; }
    """

    BINDINGS = [
        ("ctrl+b", "toggle_mode", "Switch mode"),
        ("escape", "cancel_task", "Cancel"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+y", "copy_transcript", "Copy log"),
        ("ctrl+g", "copy_output", "Copy output"),
    ]

    def __init__(self):
        super().__init__()
        self.mode = "build"
        self.steps = 0
        self.busy = False
        self.started = False
        self.run_id = 0
        self.state = None
        self.transcript = []
        self.last_output = ""
        self.history = []
        self.cur = None

    def compose(self) -> ComposeResult:
        yield Static(render_banner(), id="banner")
        yield Log(id="log", highlight=True, wrap=True)
        with Vertical(id="bottom"):
            yield Static(self.status_line(), id="status")
            yield Input(placeholder=MODES["build"]["placeholder"], id="prompt")
        yield Footer()

    def log_widget(self):
        return self.query_one("#log", RichLog)

    def prompt_widget(self):
        return self.query_one("#prompt", Input)

    def status_line(self):
        m = MODES[self.mode]
        return f" {m['label']}  ·  {model}  ·  steps {self.steps}  ·  click to expand  ·  esc cancel  ·  ctrl+b switch"

    def refresh_status(self):
        self.query_one("#status", Static).update(self.status_line())

    def apply_mode_style(self):
        m = MODES[self.mode]
        p = self.prompt_widget()
        p.placeholder = m["placeholder"]
        p.styles.border = ("round", m["border"])
        self.refresh_status()

    def action_toggle_mode(self):
        self.mode = "bash" if self.mode == "build" else "build"
        self.apply_mode_style()

    def action_cancel_task(self):
        if self.busy:
            self.workers.cancel_group(self, "task")

    def write_styled(self, text, style=""):
        self.append_block(Block("line", text, rend=Text(text, style=style)))

    def stream_reasoning(self, text):
        if self.cur is None:
            self.cur = Block("reasoning", "", rend=Text(), foldable=True, collapsed=True, live=True)
            self.history.append(self.cur)
            for r in self.cur.render():
                self.log_widget().write(r)
        self.cur.body += text
        self.cur.rend.append(text)
        if not self.cur.collapsed:
            self.log_widget().write(Text(text))

    def finalize_reasoning(self):
        if self.cur is not None:
            self.cur.live = False
            self.transcript.append(self.cur.body)
            self.cur = None
            self.rebuild_log()

    def append_block(self, block):
        self.history.append(block)
        if block.kind == "result":
            self.transcript.append(f"exit={block.rc}\n{block.body}")
        elif block.kind == "action":
            self.transcript.append(f"$ {block.body}")
        else:
            self.transcript.append(block.body)
        for r in block.render():
            self.log_widget().write(r)

    def rebuild_log(self):
        self.log_widget().clear()
        for block in self.history:
            for r in block.render():
                self.log_widget().write(r)

    def on_fold(self, id):
        for block in self.history:
            if block.id == id:
                block.collapsed = not block.collapsed
                self.rebuild_log()
                self.refresh_status()
                return

    def copy_content(self, content, label):
        if not content:
            self.write_styled(f"no {label} to copy", "yellow")
            return
        try:
            self.copy_to_clipboard(content)
        except Exception as e:
            self.write_styled(f"copy failed: {e}", "red")
            return
        n = len(content.splitlines())
        self.write_styled(f"copied {label} ({n} lines)", "bold green")

    def action_copy_transcript(self):
        self.copy_content("\n".join(self.transcript).strip("\n"), "log")

    def action_copy_output(self):
        self.copy_content(self.last_output.rstrip("\n"), "last output")

    def handle_event(self, event):
        if "_run" in event and event["_run"] != self.run_id:
            return
        t = event["type"]
        if t == "reasoning_token":
            self.stream_reasoning(event["text"])
        elif t == "action":
            self.finalize_reasoning()
            self.append_block(Block("action", event["command"], foldable=True, collapsed=False))
        elif t == "result":
            self.finalize_reasoning()
            self.steps += 1
            output = event["output"].rstrip("\n")
            foldable = collapse_output and len(output.splitlines()) > fold_lines
            self.append_block(Block("result", output, rc=event["returncode"], foldable=foldable, collapsed=foldable))
            self.last_output = event["output"]
            self.refresh_status()
        elif t == "error":
            self.finalize_reasoning()
            self.write_styled(f"agent error: {event['message']}", "bold red")
        elif t == "status":
            self.finalize_reasoning()
            status = event.get("status")
            if status == "complete":
                self.write_styled("task complete", "bold green")
            elif status == "stopped":
                self.write_styled(f"stopped: {event['reason']}", "bold yellow")
            elif status == "cancelled":
                self.write_styled("cancelled", "bold yellow")
        elif t == "done":
            self.finalize_reasoning()
            self.busy = False
            self.prompt_widget().disabled = False
            self.prompt_widget().focus()
            self.write_styled("-" * 40, "dim")
        elif t == "user":
            self.finalize_reasoning()
            self.write_styled(f"\n> {event['text']}\n", "bold #38bdf8")

    def start_worker(self, coro_fn):
        self.busy = True
        self.prompt_widget().disabled = True
        self.run_id += 1
        rid = self.run_id

        async def wrapped():
            try:
                await coro_fn(lambda e: self.handle_event({**e, "_run": rid}))
            except asyncio.CancelledError:
                self.handle_event({"type": "status", "status": "cancelled", "_run": rid})
            except Exception as e:
                self.handle_event({"type": "error", "message": str(e), "_run": rid})
            finally:
                self.handle_event({"type": "done", "_run": rid})

        self.run_worker(wrapped(), group="task", exclusive=False)

    def on_input_submitted(self, event):
        text = event.value.strip()
        self.prompt_widget().clear()
        if not text:
            return
        if self.busy:
            self.write_styled("a task is still running (esc to cancel)", "yellow")
            return
        if not self.started:
            self.query_one("#banner", Static).remove()
            self.started = True
        self.handle_event({"type": "user", "text": text})

        if self.mode == "build":
            if self.state is None:
                self.state = init_state()

            async def run(emit):
                await agent(text, emit=emit, state=self.state)

            self.start_worker(run)
        else:
            async def run(emit):
                result = await run_bash_command(text)
                emit({"type": "result", "returncode": result["returncode"], "output": result["output"]})

            self.start_worker(run)


def main():
    SadhanApp().run()


if __name__ == "__main__":
    main()