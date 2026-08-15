# sadhan

A minimal AI harness built from scratch, functional (not class-based), designed to run local models via Ollama through a real bash-execution loop.

Built as a learning project documenting an [ongoing blog series](https://blog.gauresh.art/series/ai-harness-engineering) on what actually makes an AI agent harness work, not just a bigger model.

## What this is

`sadhan` gives a local LLM (currently tested with `qwen3.5:4b` via Ollama) a real, working agent loop: it can reason about a task, execute a single bash command per turn, see the result, and keep going until it completes the task or hits a hard limit.

It's intentionally minimal. Inspired by [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent), but built independently with a different architecture, functional instead of class-based, custom XML-tag parsing instead of native tool-calling.

## Status

Early, active development. Not production-ready. Currently missing:
- No task-completion verification (the model's own "done" claim is trusted as-is)
- No persistent environment (venv/cwd doesn't survive across separate commands yet)
- No vision/screenshot support yet
- No command safety filtering (e.g. nothing currently blocks a destructive command)

## How it works
```
main.py → CLI loop, takes tasks one at a time
└── agent.py → the actual agent loop: query → parse → execute → repeat
├── llm_call.py → talks to Ollama, adds assistant message to state
├── parser.py → extracts <reasoning> and <action> from model output
├── bash.py → executes the action as a real subprocess
└── state.py → tracks messages, step count, error count
config.py → model name, step limit, error limit, working directory
prompt.py → system prompt defining the response format and rules

```
Each loop iteration:
1. The model is sent the full message history and responds with exactly one `<reasoning>` block and one `<action>` block.
2. The action is parsed out and, unless it's the completion signal, executed as a real bash command in the configured working directory.
3. The command's output is fed back into the message history as the next turn.
4. This repeats until the model executes `echo TASK_COMPLETE` as its action, or a step/error limit is hit.

## Setup

```bash
git clone https://github.com/GaureshArt/sadhan.git
cd sadhan
pip install ollama
```

Edit `config.py` to set your model name and working directory:

```python
model = 'qwen3.5:4b'
step_limit = 30
max_errors = 4
cwd = "/path/to/your/project"
```

Make sure Ollama is running and the model is pulled:

```bash
ollama pull qwen3.5:4b
```

## Usage

```bash
python main.py
```

You'll be prompted for a task. It runs until completion or a limit is hit, then prompts for the next task.

## Roadmap

- [ ] Verify task completion against real evidence, not just the model's claim
- [ ] Persistent working state across related tasks (a notes file, not full context replay)
- [ ] Command safety filtering (block destructive commands like `git push`, `rm -rf`)
- [ ] Manual screenshot-as-context support for visual tasks
- [ ] Playwright MCP integration for automated visual verification

## Why "sadhan"

Sadhan (साधन) comes from the Sanskrit root साध् ("to accomplish") — it means the means by which something gets done. An instrument, an agent, even a weapon in older usage, whatever tool actually gets you to the goal.

That's the idea here. A small local model often can't finish a real task alone. Wrapped in sadhan, it has a means to get there, and a way to actually verify it did.

## License
MIT License