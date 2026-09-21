# sadhan

A self-contained AI agent harness: any LLM drives real bash tool calls in a persistent shell, with a terminal UI. Call it once, and it explores your project, runs commands, observes results, and keeps going until the task is done.

`sadhan` connects an LLM to a working directory through OpenAI-style function calling. It is provider-agnostic — run it against local models via Ollama or any LiteLLM-compatible cloud provider — and it treats every model interaction as a genuine tool call: exactly one bash command per action, real output fed back to the model, and a persistent shell so state (cwd, exports, activated venvs) survives between calls.

## Features

- **Real tool execution** — the `run_bash` function schema is sent to the model; each call runs one command in a persistent `bash` subprocess, and `returncode + output` are returned as a valid `tool` message so the conversation stays correct.
- **Robust tool calling** — native `tool_calls` when the provider supports it, plus an automatic fallback that extracts inline-JSON tool calls from content/reasoning for models that emit calls tag-style. Any JSON artifact is scrubbed from the reasoning display; final JSON wrappers are unwrapped into plain answers.
- **Per-action reasoning** — a short `✦ reason` line is shown before each command, extracted from the tool call's `reason` field or the model's own reasoning stream.
- **Provider-agnostic** — Ollama models are auto-discovered; OpenAI, Anthropic, Gemini, Groq, DeepSeek, Mistral, xAI, Cohere, Together, Fireworks, OpenRouter, Azure, Bedrock and Vertex AI are available from a built-in catalog once the matching API key is set.
- **Terminal UI** — dual-mode TUI: `build` (describe a task) and `bash` (drop to a real shell, same persistent session). Results fold/collapse on click; `ctrl+y` copies the log.
- **Sessions** — every run is streamed to `~/.sadhan/sessions/<cwd-slug>/<timestamp>.jsonl`; browse, rename, and reload previous sessions.
- **Safety rails** — destructive commands (sudo, `rm -rf`, force-pushed/reset git, interactive editors, mkfs/dd, …) are blocked; commands time out after 60s; output is capped; the model is confined to the working directory.
- **No build-system hooks, no classes** — a small, functional Python codebase you can read top to bottom.

## Architecture

```
src/sadhan/
├── __init__.py      entry-point helpers (workdir resolution, error handling)
├── main.py          minimal one-shot CLI loop (python -m sadhan.main)
├── tui.py           Textual terminal UI, dual build/bash modes, model & session pickers
├── agent.py         the agent loop: call → tool → observe → repeat, event stream
├── llm_call.py      streams a completion with the tool schema, returns a Turn
│                    (content + tool_calls); native calls + inline-JSON fallback;
│                    JSON scrubbing + final-wrapper unwrapping
├── llms/            provider-agnostic model layer
│   ├── registry.py  model catalog: Ollama discovery + LiteLLM providers, keys, env
│   └── client.py    async LiteLLM connector; uniform streaming for every provider
├── tools.py         the run_bash tool as a Pydantic model → OpenAI function schema
├── bash.py          persistent shell: spawn, run, timeout, output cap, block list
├── prompt.py        system prompt: environment, working-directory boundary,
│                    how to act, finishing rules, recovery example
├── config.py        model, step/error limits, timeout, blocked patterns, fold opts
├── sessions.py      JSONL session storage per working directory
├── state.py         per-run state: messages, call/error counts, step limits
└── theme.py         TUI colors
```

### The loop

1. The conversation (system prompt, user task, prior assistant/tool pairs) is sent with the `run_bash` function schema.
2. The model responds either with a tool call — `{command, reason}` — or, when done, a plain final message.
3. Each call runs exactly one bash command in the persistent shell; `returncode` and output come back as a `tool` message.
4. A reasoning line (`✦ {reason}`) is shown for each call in the TUI.
5. The loop repeats until the model replies with no tool call (completion) or a step/error limit is reached.

### Tool calling in detail

- The tool schema is built from `RunBash` (`tools.py`) and sent as OpenAI-style `tools` to the provider.
- Native providers stream `tool_calls` deltas, which are accumulated into the assistant message.
- Models that emit calls as inline JSON (in `content` or `reasoning_content`) are handled by a parser that extracts `{"name": "...", "arguments": {...}}` objects and converts them into real tool calls.
- Final messages are unwrapped: `{"answer": "...", "test_result", ...}`-style wrappers are reduced to plain text, and any remaining JSON is stripped from the streamed display — you only ever see reasoning and commands, never `tool_call_id`s or raw schema.

## Setup

Requires Python 3.12+.

```bash
pip install --pre sadhan          # alpha release; --pre not needed once stable
```

Or, from a checkout:

```bash
git clone https://github.com/GaureshArt/sadhan.git
cd sadhan
uv sync                      # or: python -m pip install -e .
```

The `sadhan` and `sadhan-tui` console scripts are installed with the package.

### Working directory

The working directory is the current directory by default, or an explicit path:

```bash
sadhan                        # work in the current directory
sadhan /path/to/project       # work elsewhere
sadhan-tui ~/projects/app     # same choices, for the terminal UI
```

The model is confined to that directory: it may traverse freely inside it, but is instructed to never `cd`, write, or create anything outside of it.

## Quick start

```bash
sadhan
```

Then describe a task in the prompt and press Enter. Results stream into the log: a `✦ reason` line before each command, the command itself, its exit code and output. When the model stops calling tools, the task is complete.

- `ctrl+b` — toggle between `build` (task mode) and `bash` (raw shell on the same persistent session)
- `ctrl+o` — enter provider API keys
- `ctrl+s` — browse sessions
- `ctrl+y` — copy the transcript
- `ctrl+q` — quit

## Models & providers

The active model comes from, in order: the `SADHAN_MODEL` environment variable, the configured default, or the first available model. In the TUI, click the model name in the header to switch.

Ollama models are detected automatically (`http://localhost:11434` by default; override with `OLLAMA_HOST` or `OLLAMA_API_BASE`):

```bash
ollama pull qwen3.5:4b
```

Cloud providers come from a built-in LiteLLM catalog and appear as `(need key)` until their credential is set. Set credentials either as environment variables or via `ctrl+o` in the TUI (stored in `~/.sadhan/keys.json` and picked up on restart):

| Provider    | Environment variable            |
| ----------- | ------------------------------- |
| OpenAI      | `OPENAI_API_KEY`                |
| Anthropic   | `ANTHROPIC_API_KEY`             |
| Gemini      | `GEMINI_API_KEY`                |
| Groq        | `GROQ_API_KEY`                  |
| DeepSeek    | `DEEPSEEK_API_KEY`              |
| Mistral     | `MISTRAL_API_KEY`               |
| xAI         | `XAI_API_KEY`                   |
| Cohere      | `COHERE_API_KEY`                |
| Together    | `TOGETHERAI_API_KEY`            |
| Fireworks   | `FIREWORKS_API_KEY`             |
| OpenRouter  | `OPENROUTER_API_KEY`            |
| Azure       | `AZURE_API_KEY`                 |
| Bedrock     | `AWS_ACCESS_KEY_ID`             |
| Vertex AI   | `GOOGLE_APPLICATION_CREDENTIALS`|

Any other model id can be added with `SADHAN_MODELS` (comma-separated) and forced with `SADHAN_MODEL`.

## Configuration

Runtime behavior is configured in `src/sadhan/config.py` (or via the environment variables above):

```python
model = 'qwen3.5:4b'      # default model id (bare names → ollama/<name>)
step_limit = 30           # max tool steps per task
max_errors = 4            # tolerate this many model/tool errors before stopping
timeout = 60              # per-command timeout (seconds)
max_output_bytes = 100_000  # per-command output cap
fold_lines = 8            # TUI: collapse results longer than this
collapse_output = True    # TUI: start results collapsed
```

### Safety

Before running, each command is checked against `blocked_patterns` — sudo/su elevation, shutdown/reboot, shell bombs, `rm -rf`/`rm -f`, mkfs, `dd` to raw devices, interactive editors (`vim`/`nano`), and destructive git operations (`push --force`, `reset --hard`, `clean -fd`, etc.). Blocked commands return `[BLOCKED COMMAND]` without executing.

## Status

Early, active development (alpha). Current limitations:

- Completion is determined by the model stopping tool calls — not yet verified against real evidence.
- No vision/screenshot input support.
- The working-directory boundary is enforced via the system prompt, not a syscall-level sandbox.

## Roadmap

- [ ] Verify task completion against real evidence, not just the model's claim
- [ ] Persistent working state across related tasks (a notes file, not full context replay)
- [ ] Syscall-level sandboxing in addition to the prompt boundary
- [ ] Manual screenshot-as-context support for visual tasks
- [ ] Playwright MCP integration for automated visual verification

## Why "sadhan"

Sadhan (साधन) comes from the Sanskrit root साध् ("to accomplish") — the means by which something gets done: an instrument, an agent, a tool that actually gets you to the goal. The idea here is that a model — especially a small local one — often can't finish a real task alone. Wrapped in sadhan, it has a means to get there.

## More reading

The design decisions behind this harness are discussed in [Demystifying AI Harnesses](https://blog.gauresh.art/demystifying-ai-harnesses), part of an ongoing [AI harness engineering series](https://blog.gauresh.art/series/ai-harness-engineering).

## License

MIT