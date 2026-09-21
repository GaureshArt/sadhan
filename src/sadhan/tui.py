import asyncio
import os

from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, ListItem, ListView, RichLog, Select, Static

from .agent import agent
from .bash import run_bash_command
from .config import collapse_output, fold_lines
from .llms import PROVIDER_ENV, discover, registry, save_keys
from .state import init_state
from . import theme
from . import sessions
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
    def __init__(self, kind, body="", rc=None, foldable=False, collapsed=False, style="dim"):
        global uid_counter
        uid_counter += 1
        self.id = uid_counter
        self.kind = kind
        self.body = body
        self.rc = rc
        self.foldable = foldable
        self.collapsed = collapsed
        self.style = style

    def n_lines(self):
        return len(self.body.splitlines())

    def render(self):
        if self.kind == "user":
            t = Text.assemble(
                ("❯ ", f"bold {theme.ACCENT}"),
                (self.body, f"bold {theme.USER}"),
            )
            return [t]

        if self.kind == "action":
            head = f"{self.body.splitlines()[0]}" + (" …" if self.n_lines() > 1 else "")
            t = Text.assemble(
                ("$ ", f"bold {theme.ACTION}"),
                (head, f"{theme.ACTION_FG} {theme.ACTION_BG}"),
            )
            if self.collapsed:
                return [fold_mark(t, self.id)]
            return [
                fold_mark(Text.assemble(
                    ("$ ", f"bold {theme.ACTION}"),
                    (self.body, f"{theme.ACTION_FG} {theme.ACTION_BG}"),
                ), self.id),
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

        return [Text(self.body, self.style)]


MODES = {
    "build": {"border": theme.BORDER_FOCUS, "placeholder": "describe a task…", "label": "build", "hint": "ctrl+b bash"},
    "bash": {"border": theme.ACTION, "placeholder": "$ shell command", "label": "bash", "hint": "ctrl+b build"},
}


class SadhanApp(App):
    TITLE = "sadhan"
    SUB_TITLE = "ai harness"
    AUTO_FOCUS = "#prompt"
    ENABLE_COMMAND_PALETTE = False

    CSS = f"""
    Screen {{ background: {theme.BG}; }}

    #header {{
        height: 2;
        margin: 0 1 0 1;
        padding: 0 1;
        border-bottom: solid {theme.BORDER};
    }}
    #brand {{ width: auto; padding: 0 1 0 0; color: {theme.ACCENT}; text-style: bold; }}
    #ver {{ width: auto; padding: 0 2 0 2; color: {theme.MUTED}; }}
    #hf {{ width: 1fr; }}
    #status {{ width: auto; padding: 0 1 0 1; color: {theme.MUTED}; }}
    #model-pick {{ width: auto; max-width: 36; }}

    #log-panel {{
        height: 1fr;
        margin: 1 1 0 1;
        border: round {theme.BORDER};
        background: {theme.PANEL};
    }}
    #log-panel #log {{
        height: 100%;
        padding: 0 1;
        background: {theme.PANEL};
    }}

    #input-bar {{
        height: 3;
        margin: 1 1 1 1;
    }}
    #pg {{
        width: auto;
        padding: 0 1 0 0;
        text-style: bold;
        color: {theme.ACCENT};
    }}
    #prompt {{
        height: 3;
        width: 1fr;
        border: round {theme.BORDER_FOCUS};
        background: {theme.PANEL_HI};
        color: {theme.FG};
    }}
    #prompt:disabled {{
        border: round {theme.BORDER};
        color: {theme.MUTED};
        background: {theme.PANEL};
    }}
    #input-bar.build #pg {{ color: {theme.ACCENT}; }}
    #input-bar.bash #pg {{ color: {theme.CYAN}; }}
    #input-bar.build #prompt {{ border: round {theme.ACCENT}; }}
    #input-bar.bash #prompt {{ border: round {theme.CYAN}; }}
    #hint {{
        width: auto;
        padding: 0 1 0 1;
        color: {theme.MUTED};
    }}

    Footer {{ background: {theme.PANEL}; }}
    """

    BINDINGS = [
    ("ctrl+b", "toggle_mode", "Switch mode"),
    ("ctrl+o", "open_keys", "Keys"),
    ("ctrl+s", "browse_sessions", "Sessions"),
    ("escape", "cancel_task", "Cancel"),
    ("ctrl+q", "quit", "Quit"),
    ("ctrl+y", "copy_transcript", "Copy log"),
    ]

    def __init__(self):
        super().__init__()
        self.register_theme(theme.THEME)
        self.theme = theme.THEME.name
        self.mode = "build"
        self.steps = 0
        self.tokens = 0
        self.busy = False
        self.run_id = 0
        self.state = None
        self.transcript = []
        self.history = []
        self.reasoning_active = False
        self.reasoning_buffer = []
        self.reasoning_accum = []
        self._model_ui_busy = False
        self._spin = 0
        self._spin_frames = "◐◓◑◒"

    def on_mount(self):
        self.apply_mode_style()
        self.set_interval(0.18, self._tick_spin)

    def _tick_spin(self):
        if self.busy:
            self._spin = (self._spin + 1) % len(self._spin_frames)
            self.refresh_status()

    def action_browse_sessions(self):
        paths = sessions.list_sessions()
        if not paths:
            self.write_line("no sessions in this directory yet", f"bold {theme.WARN}")
            return
        self.push_screen(SessionPicker(paths), self.load_session)

    def load_session(self, path):
        if path is None:
            return
        messages = sessions.load_session(path)
        self.state = init_state(messages=messages)
        self.state["session_path"] = path
        self.steps = 0
        self.tokens = 0
        self.history = []
        self.transcript = []
        self.log_widget().clear()
        self.write_line(f"resumed {path.stem} ({len(messages)} messages)", f"bold {theme.OK}")

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("❖ sadhan", id="brand"),
            Static("ai harness", id="ver"),
            Static("", id="hf"),
            Static(self.status_line(), id="status"),
            Select(
                registry.options(),
                id="model-pick",
                allow_blank=len(registry) == 0,
                value=registry.active.name if registry.active else Select.NULL,
                prompt="select a model",
                compact=True,
            ),
            id="header",
        )
        yield Vertical(
            Log(id="log", highlight=True, wrap=True),
            id="log-panel",
        )
        yield Horizontal(
            Static("❯", id="pg"),
            Static(MODES["build"]["hint"], id="hint"),
            Input(placeholder=MODES["build"]["placeholder"], id="prompt"),
            id="input-bar",
        )
        yield Footer()

    def log_widget(self):
        return self.query_one("#log", RichLog)

    def prompt_widget(self):
        return self.query_one("#prompt", Input)

    def _fmt_tokens(self):
        if self.tokens >= 1000:
            return f"{self.tokens / 1000:.1f}k"
        return str(self.tokens)

    def status_line(self):
        dot = "●"
        dot_color = theme.ACCENT if self.mode == "build" else theme.CYAN
        parts = [
            Text(f"{dot} {self.mode}  ", style=f"bold {dot_color}"),
            Text(f"{self.steps} steps  ·  {self._fmt_tokens()} tokens", style=theme.MUTED),
        ]
        if self.busy:
            parts.insert(0, Text(self._spin_frames[self._spin] + "  ", style=f"bold {theme.ACCENT2}"))
        return Text.assemble(*parts)

    def refresh_status(self):
        self.query_one("#status", Static).update(self.status_line())

    def apply_mode_style(self):
        m = MODES[self.mode]
        self.query_one("#input-bar", Horizontal).set_classes(self.mode)
        self.query_one("#hint", Static).update(m["hint"])
        self.prompt_widget().placeholder = m["placeholder"]
        self.refresh_status()

    def action_toggle_mode(self):
        self.mode = "bash" if self.mode == "build" else "build"
        self.apply_mode_style()

    def action_open_keys(self):
        self.push_screen(KeyModal(list(PROVIDER_ENV.items())), self.apply_keys)

    def apply_keys(self, keys):
        if not keys:
            return
        save_keys(keys)
        for var, value in keys.items():
            os.environ[var] = value
        discover(force=True)
        select = self.query_one("#model-pick", Select)
        self._model_ui_busy = True
        select.set_options(registry.options())
        select.value = registry.active.name if registry.active else Select.NULL
        self._model_ui_busy = False
        self.write_line(f"saved {len(keys)} api keys", f"bold {theme.OK}")

    def on_select_changed(self, event):
        if self._model_ui_busy:
            return
        if event.select.id != "model-pick" or event.value is Select.NULL:
            return
        if event.value == (registry.active.name if registry.active else None):
            return
        event.stop()
        registry.set_active(event.value)
        self.write_line(f"model: {registry.active.display}", f"bold {theme.ACCENT2}")

    def action_cancel_task(self):
        if self.busy:
            self.workers.cancel_group(self, "task")

    def write_line(self, text, style="dim"):
        self.append_block(Block("line", text, style=style))

    def stream_reasoning(self, text):
        if not self.reasoning_active:
            self.reasoning_active = True
            self.reasoning_buffer = []
            self.reasoning_accum = []
        self.reasoning_buffer.append(text)
        self.reasoning_accum.append(text)
        joined = "".join(self.reasoning_buffer)
        if "\n" in joined:
            parts = joined.split("\n")
            rest = parts.pop()
            for line in parts:
                self.log_widget().write(Text(line, style=f"italic {theme.REASON}"))
            self.reasoning_buffer = [rest]

    def finalize_reasoning(self):
        if self.reasoning_active:
            rest = "".join(self.reasoning_buffer)
            if rest:
                self.log_widget().write(Text(rest, style=f"italic {theme.REASON}"))
            self.transcript.append("".join(self.reasoning_accum))
            self.reasoning_active = False
            self.reasoning_buffer = []

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
            self.write_line("nothing to copy", f"bold {theme.WARN}")
            return
        self.copy_to_clipboard(content)
        self.write_line(f"copied ({len(content.splitlines())} lines)", f"bold {theme.OK}")

    def handle_event(self, event):
        if "_run" in event and event["_run"] != self.run_id:
            return
        t = event["type"]
        if t == "reasoning_token":
            self.stream_reasoning(event["text"])
        elif t == "reason":
            self.finalize_reasoning()
            self.write_line(f"✦ {event['text']}", f"italic {theme.REASON}")
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
            self.write_line(f"error: {event['message']}", f"bold {theme.FAIL}")
        elif t == "status":
            self.finalize_reasoning()
            if event.get("status") == "stopped":
                self.write_line(f"stopped: {event['reason']}", f"bold {theme.WARN}")
            elif event.get("status") == "cancelled":
                self.write_line("cancelled", f"bold {theme.WARN}")
        elif t == "done":
            self.finalize_reasoning()
            self.busy = False
            self.prompt_widget().disabled = False
            self.prompt_widget().focus()
            self.write_line("done", f"bold {theme.OK}")
            self.refresh_status()
        elif t == "user":
            self.finalize_reasoning()
            self.append_block(Block("user", event["text"]))
        elif t == "answer":
            self.finalize_reasoning()
            self.write_line(event["text"], f"bold {theme.OK}")

    def start_worker(self, coro_fn):
        self.busy = True
        self.prompt_widget().disabled = True
        self.run_id += 1
        rid = self.run_id

        async def wrapped():
            try:
                await coro_fn(lambda e: self.handle_event({**e, "_run": rid}))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.handle_event({"type": "error", "message": str(e), "_run": rid})
            finally:
                self.handle_event({"type": "done", "_run": rid})

        self.run_worker(wrapped(), group="task", exclusive=False)

    def on_input_submitted(self, event):
        if event.input.id != "prompt":
            return
        text = event.value.strip()
        self.prompt_widget().clear()
        if not text:
            return
        if self.busy:
            self.write_line("still running, esc to cancel", f"bold {theme.WARN}")
            return
        self.handle_event({"type": "user", "text": text})

        if self.mode == "build":
            if self.state is None:
                self.state = init_state()
                self.state["session_path"] = sessions.new_session_path()

            async def run(emit):
                await agent(text, emit=emit, state=self.state)

            self.start_worker(run)
        else:
            async def run(emit):
                result = await run_bash_command(text)
                emit({"type": "result", "returncode": result["returncode"], "output": result["output"]})

            self.start_worker(run)




class RenamePrompt(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, current_name):
        super().__init__()
        self.current_name = current_name or ""

    def compose(self):
        yield Input(value=self.current_name, placeholder="session name…", id="rename_input")

    def on_input_submitted(self, event):
        event.stop()
        self.dismiss(event.value.strip())

    def action_cancel(self):
        self.dismiss(None)


class KeyModal(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    #key-title { height: auto; padding: 1 2; text-style: bold; }
    #key-scroll { width: 60%; height: 80%; border: round $border; margin: 1 5; padding: 1 2; }
    .key-provider { color: $text; text-style: bold; padding-top: 1; }
    .key-var { color: $text-muted; }
    #key-save { margin: 1 2; width: 16; }
    """

    def __init__(self, providers):
        super().__init__()
        self.providers = providers

    def compose(self):
        yield Static("API keys", id="key-title")
        with VerticalScroll(id="key-scroll"):
            for name, var in self.providers:
                yield Static(f"{name}", classes="key-provider")
                yield Static(f"[dim]{var}[/dim]", classes="key-var")
                yield Input(placeholder=var, password=True, id=var)
            yield Button("Save", id="key-save")

    def on_button_pressed(self, event):
        if event.button.id != "key-save":
            return
        keys = {}
        for _name, var in self.providers:
            value = self.query_one(f"#{var}", Input).value.strip()
            if value:
                keys[var] = value
        self.dismiss(keys)

    def action_cancel(self):
        self.dismiss(None)



class SessionPicker(ModalScreen):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("r", "rename", "Rename"),
    ]

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def compose(self):
        yield ListView(*[ListItem(Label(sessions.session_label(p))) for p in self.paths])

    def on_mount(self):
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event):
        self.dismiss(self.paths[event.list_view.index])

    def action_cancel(self):
        self.dismiss(None)

    def action_rename(self):
        lv = self.query_one(ListView)
        idx = lv.index
        if idx is None:
            return
        path = self.paths[idx]
        current = sessions.read_meta(path).get("name")

        def apply_rename(new_name):
            if new_name:
                sessions.write_meta(path, new_name)
                lv.children[idx].query_one(Label).update(sessions.session_label(path))

        self.app.push_screen(RenamePrompt(current), apply_rename)

def main():
    import sys

    from . import config

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        try:
            config.cwd = config.resolve_workdir(args[0])
        except ValueError as e:
            print(f"sadhan-tui: error: {e}", file=sys.stderr)
            sys.exit(1)

    from .llms import discover
    from .config import model as default_model

    discover(default_model=default_model, force=True)
    SadhanApp().run()


if __name__ == "__main__":
    main()