import asyncio

from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Footer, Input, RichLog, Static

from .agent import agent
from .bash import run_bash_command
from .config import collapse_output, fold_lines, model
from .state import init_state
from . import theme

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
    def __init__(self, kind, body="", rc=None, foldable=False, collapsed=False):
        global uid_counter
        uid_counter += 1
        self.id = uid_counter
        self.kind = kind
        self.body = body
        self.rc = rc
        self.foldable = foldable
        self.collapsed = collapsed

    def n_lines(self):
        return len(self.body.splitlines())

    def render(self):
        if self.kind == "user":
            return [Text(f"> {self.body}", f"bold {theme.USER}")]

        if self.kind == "action":
            head = f"$ {self.body.splitlines()[0]}" + (" …" if self.n_lines() > 1 else "")
            if self.collapsed:
                return [fold_mark(Text(head, f"{theme.ACTION_FG} {theme.ACTION_BG}"), self.id)]
            return [
                fold_mark(Text(f"$ {self.body}", f"{theme.ACTION_FG} {theme.ACTION_BG}"), self.id),
            ]

        if self.kind == "result":
            color = theme.OK if self.rc == 0 else theme.FAIL
            tag = f"exit {self.rc}"
            if not self.foldable:
                return [Text(tag, color), Text(self.body, f"{theme.OUT_FG} {theme.OUT_BG}")]
            if self.collapsed:
                return [fold_mark(Text(f"{tag}  ({self.n_lines()} lines, collapsed)", color), self.id)]
            return [
                fold_mark(Text(tag, color), self.id),
                Text(self.body, f"{theme.OUT_FG} {theme.OUT_BG}"),
            ]

        return [Text(self.body, "dim")]


MODES = {
    "build": {"border": theme.BORDER_FOCUS, "placeholder": "describe a task…  ctrl+b for bash", "label": "build"},
    "bash": {"border": theme.ACTION, "placeholder": "$ shell command  ctrl+b for build", "label": "bash"},
}


class SadhanApp(App):
    TITLE = "sadhan"
    AUTO_FOCUS = "#prompt"

    CSS = f"""
    Screen {{ background: {theme.BG}; }}
    #banner {{ height: auto; padding: 1 0 0 0; }}
    #log {{
        height: 1fr;
        padding: 1 2 0 2;
        margin: 1 1 0 1;
    }}
    #status {{
        height: 1;
        padding: 0 2;
        color: {theme.DIM};
    }}
    #prompt {{
        margin: 1 1 1 1;
        border: round {theme.BORDER};
    }}
    """

    BINDINGS = [
        ("ctrl+b", "toggle_mode", "Switch mode"),
        ("escape", "cancel_task", "Cancel"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+y", "copy_transcript", "Copy log"),
    ]

    def __init__(self):
        super().__init__()
        self.mode = "build"
        self.steps = 0
        self.tokens = 0
        self.busy = False
        self.started = False
        self.run_id = 0
        self.state = None
        self.transcript = []
        self.history = []
        self.reasoning_active = False
        self.reasoning_buffer = []

    def compose(self) -> ComposeResult:
        yield Static(theme.banner(), id="banner")
        yield Log(id="log", highlight=True, wrap=True)
        yield Static(self.status_line(), id="status")
        yield Input(placeholder=MODES["build"]["placeholder"], id="prompt")
        yield Footer()

    def log_widget(self):
        return self.query_one("#log", RichLog)

    def prompt_widget(self):
        return self.query_one("#prompt", Input)

    def status_line(self):
        m = MODES[self.mode]
        return f" {m['label']}  ·  {model}  ·  {self.steps} steps  ·  {self.tokens} tokens"

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

    def write_line(self, text, style="dim"):
        self.append_block(Block("line", text))
        self.log_widget().write(Text(text, style=style))

    def stream_reasoning(self, text):
        if not self.reasoning_active:
            self.reasoning_active = True
            self.reasoning_buffer = []
            self.log_widget().write(Text("", style=f"bold {theme.REASON}"))
        self.reasoning_buffer.append(text)
        self.log_widget().write(Text(text, style=theme.REASON))

    def finalize_reasoning(self):
        if self.reasoning_active:
            self.transcript.append("".join(self.reasoning_buffer))
            self.reasoning_active = False
            self.reasoning_buffer = []
            self.log_widget().write(Text(""))

    def append_block(self, block):
        self.history.append(block)
        if block.kind == "result":
            self.transcript.append(f"exit={block.rc}\n{block.body}")
        elif block.kind == "action":
            self.transcript.append(f"$ {block.body}")
        elif block.kind != "line":
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
                return

    def action_copy_transcript(self):
        content = "\n".join(self.transcript).strip("\n")
        if not content:
            self.write_line("nothing to copy", "yellow")
            return
        self.copy_to_clipboard(content)
        self.write_line(f"copied ({len(content.splitlines())} lines)", "bold green")

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
            self.refresh_status()
        elif t == "usage":
            self.tokens += event["tokens"]
            self.refresh_status()
        elif t == "error":
            self.finalize_reasoning()
            self.write_line(f"error: {event['message']}", "bold red")
        elif t == "status":
            self.finalize_reasoning()
            if event.get("status") == "stopped":
                self.write_line(f"stopped: {event['reason']}", "bold yellow")
            elif event.get("status") == "cancelled":
                self.write_line("cancelled", "bold yellow")
        elif t == "done":
            self.finalize_reasoning()
            self.busy = False
            self.prompt_widget().disabled = False
            self.prompt_widget().focus()
            self.write_line("done", "bold green")
        elif t == "user":
            self.finalize_reasoning()
            self.append_block(Block("user", event["text"]))

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
            self.write_line("still running, esc to cancel", "yellow")
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