# code-swap

**One CLI. Any model. Smart routing.**

Stop juggling API keys and model-specific clients. code-swap gives you Claude, GPT, Gemini, DeepSeek, Llama, Mistral, and 200+ more models through a single OpenRouter API key -- from one terminal command.

## Why code-swap?

- **One key, every model.** One OpenRouter API key replaces separate accounts for Anthropic, OpenAI, Google, Meta, and the rest. Switch models mid-conversation with `/model`.
- **Smart routing picks the right model for you.** Enable `/auto` and code-swap classifies your prompt -- sending code tasks to Claude, research to DeepSeek, reviews to Gemini, creative work to GPT. Zero manual model selection.
- **A/B test models in seconds.** `/compare` runs the same prompt through two models side by side. See which is better, cheaper, faster -- with real cost data.
- **Multi-model crews.** Orchestrate GPT planning, Claude coding, Gemini reviewing, and DeepSeek researching -- all in one command.

## Quick Start

```bash
# Install (pick one)
uv tool install code-swap
pipx install code-swap
pip install --user code-swap

# Set your OpenRouter API key (get one free at https://openrouter.ai/keys)
code-swap config --key sk-or-v1-YOUR_KEY

# Launch the REPL
code-swap
```

Or run a one-shot prompt:

```bash
code-swap ask "Explain Python's GIL in 3 sentences"
```

## Features

### Smart Router -- Let AI Pick the AI

Enable auto-routing and code-swap classifies every prompt, routing it to the best model for the job.

```
you> /auto on
  Smart routing enabled

you> Fix the race condition in worker.py
  Detected debugging task -> routing to Claude Sonnet 4.5

you> What are the tradeoffs between Redis and Memcached?
  Detected research task -> routing to DeepSeek R1

you> Review this PR for security issues
  Detected code review task -> routing to Gemini 2.5 Pro
```

### Model A/B Testing

Run the same prompt through two models. Compare quality, speed, and cost.

```
you> /compare anthropic/claude-sonnet-4-5 openai/gpt-4.1
  Comparing models... Enter a prompt.

you> Write a Python retry decorator with exponential backoff

  --- Model A: claude-sonnet-4-5 ---
  [response]
  547 tokens | $0.0084 | 2.1s

  --- Model B: gpt-4.1 ---
  [response]
  612 tokens | $0.0051 | 1.8s
```

### Multi-Model Crews

Orchestrate multiple models working together on complex tasks. The orchestrator breaks work into subtasks, dispatches them to specialists in parallel, and synthesizes the results.

```bash
# From the REPL
you> /run Implement JWT authentication for the Express API

# Or from the command line
code-swap run "Implement JWT auth" --crew full-stack --budget 5.0
```

Four built-in crew templates:

| Crew | Agents | Use Case |
|------|--------|----------|
| `default` | Claude (plan + code) + GPT (review) | General coding tasks |
| `full-stack` | GPT (plan) + Claude (code) + Gemini (review) + DeepSeek (research) | Full-stack development |
| `code-review` | Claude (analyze) + GPT (security) + Gemini (style) | Comprehensive code review |
| `research` | GPT (coordinate) + DeepSeek (reason) + Claude (synthesize) | Deep research and analysis |

### Built-in Tools

code-swap can execute tools on your behalf -- shell commands, file reads/writes, test runs, and linting. Permission controls keep you in charge.

| Tool | Permission | Description |
|------|-----------|-------------|
| `shell` | ask | Run shell commands |
| `read_file` | auto | Read file contents |
| `write_file` | ask | Write to files |
| `run_tests` | ask | Auto-detect and run pytest, jest, vitest, cargo test, go test |
| `lint` | ask | Auto-detect and run ruff, eslint, golangci-lint |

```
you> /tools
  5 tools available. Use /yolo to auto-approve all executions.

you> /yolo on
  YOLO mode enabled -- all tool executions auto-approved.
```

Or launch with `--yolo` from the command line:

```bash
code-swap --yolo
```

### Git-Aware Context

code-swap auto-detects your git repository on startup and injects branch, status, and diff context into every prompt.

```
you> /git
  Branch: feature/auth
  Status: 3 modified, 1 untracked
  Last commit: abc1234 Add login endpoint

you> /diff
  [shows current unstaged changes]

you> /repo
  [shows repository structure summary]
```

### Persistent Sessions

Save conversations, resume them later, or pick up right where you left off.

```
you> /save-session auth-work
  Session saved: auth-work (23 messages)

you> /sessions
  auth-work     23 msgs   2 min ago
  refactor-db   41 msgs   1 hour ago

you> /load-session auth-work
  Session loaded: auth-work (23 messages restored)
```

Enable `auto_resume` in config to automatically restore your last session on startup.

### Real-time Cost Tracking

Every response shows token usage and cost. Track spending across your session with `/cost`.

```
  claude-sonnet-4-5 | 1,247 in + 583 out | $0.0125 | 2.3s

you> /cost
  Session total: $0.0847 (14 requests)
  Input:  18,429 tokens
  Output:  6,215 tokens
```

## Route Table

Default model assignments when smart routing is enabled:

| Task | Model | Why |
|------|-------|-----|
| Code generation | `anthropic/claude-sonnet-4-5` | Best-in-class code quality |
| Debugging | `anthropic/claude-sonnet-4-5` | Strong reasoning about code behavior |
| Refactoring | `anthropic/claude-sonnet-4-5` | Understands large codebases |
| Code review | `google/gemini-2.5-pro` | Large context window, thorough analysis |
| Research | `deepseek/deepseek-r1` | Deep chain-of-thought reasoning |
| Creative | `openai/gpt-4.1` | Strong creative and natural language output |
| General | Your default model | Configurable fallback |

Override any route in your config:

```yaml
# ~/.code_swap.yaml
auto_route: true
route_overrides:
  code_generation: "openai/o3"
  research: "google/gemini-2.5-pro"
```

## Configuration

All settings live in `~/.code_swap.yaml`:

```yaml
api_key: sk-or-v1-your-key-here
model: anthropic/claude-sonnet-4-5
auto_save: true
auto_resume: false
auto_route: false
yolo_mode: false
max_sessions: 50
```

Manage from the CLI:

```bash
code-swap config --show          # View current config
code-swap config --key sk-or-... # Set API key
code-swap config --model openai/gpt-4.1  # Change default model
```

API key resolution order: `--api-key` flag > `OPENROUTER_API_KEY` env var > config file.

## All Commands

### CLI Commands

| Command | Description |
|---------|-------------|
| `code-swap` | Launch interactive REPL |
| `code-swap ask "prompt"` | One-shot query |
| `code-swap models` | List available models |
| `code-swap models -s "claude"` | Search models by name |
| `code-swap config` | Manage settings |
| `code-swap install` | Install globally (auto-detects uv/pipx/pip) |
| `code-swap run "task"` | Run a multi-model crew |
| `code-swap run "task" --crew full-stack` | Run with a specific crew |

### REPL Slash Commands

| Command | Description |
|---------|-------------|
| `/model <id>` | Switch model mid-conversation |
| `/compare <a> <b>` | A/B test two models |
| `/split` | Split-pane view |
| `/critique` | Self-critique the last response |
| `/auto [on\|off]` | Toggle smart routing |
| `/route` | Show current route table |
| `/tokens` | Show token usage |
| `/cost` | Show session cost breakdown |
| `/context <file>` | Load file into context (also supports `@file` syntax) |
| `/save` | Save last response to file |
| `/new` | Start a new conversation |
| `/clear` | Clear the screen |
| `/save-session <name>` | Save current session |
| `/load-session <name>` | Load a saved session |
| `/sessions` | List saved sessions |
| `/resume` | Resume last session |
| `/delete-session <name>` | Delete a saved session |
| `/git` | Show git branch and status |
| `/diff` | Show current diff |
| `/repo` | Show repository summary |
| `/tools` | List available tools |
| `/yolo [on\|off]` | Toggle auto-approve for tools |
| `/crew list\|load\|show` | Manage crew configurations |
| `/run <task>` | Run task with current crew |
| `/agents` | Show agents in current crew |
| `/status` | Show session status |
| `/help` | Show all commands |
| `/quit` | Exit |

## Requirements

- Python 3.11+
- An OpenRouter API key ([get one free](https://openrouter.ai/keys))

## Contributing

Contributions are welcome. Please open an issue first to discuss what you would like to change.

```bash
git clone https://github.com/Ola-Yeenca/code-swap.git
cd code-swap/backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT
