# sadhan

A minimal AI agent harness that connects any LLM to a real bash shell — one command per call, output fed back as real tool results, persistent session state, repeat until the task is done.

Python 3.12+ · LiteLLM-backed · runs fully local with Ollama · pre-release alpha

---

## The loop

1. The conversation, plus the currently open tool schemas, is sent to the model.
2. The model either calls a tool or sends a final message (done).
3. Each call is schema-validated, checked by before-tool hooks, then executed in a persistent shell.
4. Every result — success, error, veto — is fed back into the model's history.
5. Two budgets keep runs bounded: `max_steps` (total tool calls) and `max_consecutive_errors` (consecutive failures, refreshed by a clean step).

Design decisions are written up in [Demystifying AI Harnesses](https://blog.gauresh.art/demystifying-ai-harnesses).

## Quick start

```bash
uv sync
ollama pull qwen3.5:4b
.venv/bin/sadhan --cwd /path/to/project
```

To put `sadhan` on your PATH from a checkout:

```bash
uv tool install --editable .
```

A session:

```
sadhan> run "echo hello", then stop.

Step 1 started.
Tool Invoked: bash
Tool Result: hello
Step 2 started.
Done.
```

## CLI


| Flag         | Default                  | Meaning                                                                 |
| ------------ | ------------------------ | ----------------------------------------------------------------------- |
| `--model`    | `ollama_chat/qwen3.5:4b` | Any LiteLLM model id (`llama3.2`, `openai/gpt-…`, `anthropic/claude-…`) |
| `--api-base` | —                        | Endpoint override, e.g. a remote Ollama host                            |
| `--cwd`      | current dir              | The project directory the agent works in                                |


Cloud credentials come from the environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, …), the standard LiteLLM way. Text streams in real time; more UI polish is planned.

## Safety

- One command per call: schema-validated, executed in a persistent shell with sentinel-based output capture, a 1 MB output ceiling, and a per-command timeout (120 s default — on timeout the shell restarts, `cd` state is lost).
- The child shell's environment is scrubbed of credential-looking variables and `BASH_ENV`.
- **Policy is plugin territory**: `before_tool` hooks veto calls before execution. Vetoes return a `[BLOCKED] <reason>` tool result, so the model learns why and self-corrects — vetoes never count against the error budget.
- A first-party veto hook ships with the repo (`.sadhan/plugins/bash_safety.py`), blocking:
  - privilege escalation (`sudo`, `su`, `doas`)
  - recursive force-deletes
  - fork bombs
  - shutdown / reboot / halt / `systemctl` power actions
  - disk destroyers (`mkfs`, `wipefs`, `dd of=/dev/…`)
  - pipe-to-shell remote execution (`curl … | sh`)

A blocklist is a speed bump, not enforcement — interpreters, heredocs, and base64 pipes route around patterns. Directory confinement is prompt-based, with a subprocess sandbox on the roadmap.

## Plugins

Plugins are plain `.py` files with one entry point. Load order (first wins on name clashes):

1. built-in tools (`bash` registers first)
2. `~/.sadhan/plugins/` — your personal set, every project
3. `<project>/.sadhan/plugins/` — repo-local, commit-able

```python
# ~/.sadhan/plugins/my_guard.py
def register(host):
    async def veto(call):
        if call.name != "bash":
            return None                      # abstain: not my tool
        if "rm -rf" in call.input.get("command", ""):
            return "destructive delete"      # vetoes the call
        return None                          # no opinion: call runs
    host.before_tool(veto)
```

- `register(host)` runs once at startup; plugins may add tools (`host.add_tool`) and hooks (`host.before_tool`).
- Tools subclass `Tool`: `name`, `description`, Pydantic `params` (becomes the JSON schema the model sees), `async run(args)`.
- Hooks run in registration order on every call; the first to return a reason blocks, the rest are skipped.
- Plugins are more than tools: hooks are the seam for policy, audit, and redaction over any tool — including ones that don't exist yet.
- Broken plugins are logged and skipped; missing dependencies surface as a clear import error and are never auto-installed. **Plugins are code you trust** — they run with your rights.

## Configuration

Defaults live in `src/sadhan/config.py` (frozen, validated).


| Field                    | Default  | Effect                                          |
| ------------------------ | -------- | ----------------------------------------------- |
| `max_steps`              | 100      | Tool-call budget per run                        |
| `max_consecutive_errors` | 5        | Consecutive-failure budget                      |
| `command_timeout`        | 120 s    | Per-command timeout                             |
| `system_prompt`          | built-in | Directory boundary + one-command-per-call rules |
| `working_dir`            | cwd      | The shell's working base                        |


## Project layout

```
src/sadhan/
├── __main__.py     wiring + REPL
├── agent.py        the loop: model → hooks → tools → observe → repeat
├── provider.py     LiteLLM streaming adapter
├── messages.py     block-based conversation model (text / tool_use / tool_result)
├── event.py        typed events + EventBus with handler isolation
├── cli.py          CLI event renderer
├── state.py        per-run state, schema-versioned
├── config.py       validated defaults + system prompt
├── plugins.py      PluginHost + drop-in loader
└── tools/
    ├── base.py     Tool / Hook contracts
    ├── registry.py tool registry
    ├── shell.py    persistent bash: sentinel capture, env scrub, timeouts
    └── bash.py     the bash tool
```

The event bus is the seam between the loop and observation — renderers, sessions, and dashboards subscribe; the loop never knows they exist.

## Limitations

- Directory confinement is prompt-based, not syscall-based.
- No session persistence or context compaction yet.
- Completion is judged by the model stopping tool calls, not verified against evidence.
- The CLI is functional, not polished.

## Roadmap

- [ ] Human-approval hooks (ask / allow / deny on flagged commands)
- [ ] Session persistence (JSONL per working directory)
- [ ] Context compaction and token accounting
- [ ] Subprocess sandbox 
- [ ] MCP client support
- [ ] Per-model reasoning options

## Development

```bash
ruff check && ruff format
python -m pytest -q
```

Gate before committing: `ruff check && python -m pytest -q && python -c "import sadhan.__main__"`.

## Why "sadhan"

From the Sanskrit root साध्, "to accomplish" — the means by which something gets done. Models often can't finish real work alone. Wrapped in sadhan, they have the means.

## License

MIT