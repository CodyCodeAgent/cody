# Cody

AI coding engine with RPC Server, dynamic skills, MCP integration, and LSP intelligence.

**Core philosophy: engine first, shell second.** CLI, TUI, and Server are thin shells over a shared core engine. The Server + SDK delivery model is our differentiator — let others embed AI coding capabilities into their own systems.

## Features

- **Thinking Mode** — `--thinking` flag enables model reasoning with configurable token budget
- **Streaming Events** — Structured `StreamEvent` system: thinking, tool calls, text deltas, all in real-time
- **28 AI Tools** — File ops, search (grep/glob/patch), shell commands, undo/redo, task management, structured questions
- **11 Built-in Skills** — git, github, docker, npm, python, rust, go, java, web, cicd, testing — AI reads SKILL.md to learn usage
- **CI/CD Templates** — Ready-to-use GitHub Actions for AI code review, auto-fix, and test generation
- **RPC Server + SDK** — FastAPI HTTP/WebSocket server, Python SDK (sync + async), Go SDK, embeddable into any system
- **MCP Integration** — Connect to external MCP servers (GitHub, databases, etc.) via stdio JSON-RPC
- **LSP Intelligence** — Python (pyright), TypeScript (tsserver), Go (gopls) — diagnostics, go-to-definition, references, hover
- **Sub-Agent System** — Spawn specialized agents (code/research/test) with asyncio concurrency
- **Context Management** — Auto-compact conversations approaching token limits, smart file chunking
- **Security** — Tool-level permissions (allow/deny/confirm), path traversal protection, dangerous command detection, audit logging, rate limiting, OAuth 2.0
- **Session Persistence** — SQLite-backed multi-session management with history
- **Multi-Model** — Anthropic Claude, OpenAI GPT, Google Gemini, DeepSeek, 智谱 GLM, 阿里通义千问, and any OpenAI-compatible API via Pydantic AI

## Quick Start

```bash
# Install
git clone https://github.com/yourusername/cody.git
cd cody
pip install -e .

# Set up API key
export ANTHROPIC_API_KEY='your-key-here'

# Initialize in a project
cody init

# Run a task
cody run "create a FastAPI hello world app"

# With thinking mode
cody run --thinking "design a REST API for user management"

# Specify working directory
cody run "refactor auth.py" --workdir /path/to/project

# Interactive chat
cody chat

# Continue previous conversation
cody chat --continue

# Full-screen TUI
cody tui
```

## Four Modes of Operation

### CLI

```bash
cody run "refactor auth.py"              # One-shot task
cody run --thinking "complex analysis"   # With thinking mode
cody run -v "debug this"                 # Verbose (show tool results)
cody run --workdir /path/to/project "fix tests"  # Specify working directory
cody chat                                # Interactive REPL
cody chat --thinking                     # Chat with thinking enabled
cody chat --continue                     # Resume last session
cody chat --session abc123               # Resume specific session
cody chat --workdir /path/to/project     # Chat in specific directory
```

Chat slash commands: `/quit`, `/sessions`, `/clear`, `/help`.

### TUI (Textual)

```bash
cody tui                             # Full-screen terminal UI
cody tui --continue                  # Resume last session
cody tui --session <id>              # Resume specific session
cody tui --workdir /path/to/project  # Specify working directory
```

Features: streaming output, multi-session management, slash commands (/help, /new, /sessions, /clear), keyboard shortcuts (Ctrl+N, Ctrl+C, Ctrl+Q).

### RPC Server

```bash
cody-server                          # Default 0.0.0.0:8000
cody-server --port 9000              # Custom port
```

Endpoints: `POST /run`, `POST /run/stream` (SSE), `POST /tool`, `GET /skills`, `GET /sessions`, `WS /ws`, `GET /audit`, `GET /health`. Full docs: [docs/API.md](docs/API.md).

### Session Management

```bash
cody sessions list                   # List recent sessions
cody sessions show <id>              # Show session conversation
cody sessions delete <id>            # Delete a session
```

### Python SDK

```python
from cody import AsyncCodyClient

async with AsyncCodyClient("http://localhost:8000") as client:
    # One-shot
    result = await client.run("create hello.py")

    # Multi-turn session
    session = await client.create_session()
    await client.run("create Flask app", session_id=session.id)
    await client.run("add /health endpoint", session_id=session.id)

    # Streaming
    async for chunk in client.stream("explain this code"):
        print(chunk.content, end="")

    # Direct tool call
    result = await client.tool("read_file", {"path": "main.py"})
```

Sync version: `CodyClient`. Built-in retry with exponential backoff.

### Go SDK

```go
client := cody.NewClient("http://localhost:8000")

// One-shot
result, _ := client.Run(ctx, "create hello.py")
fmt.Println(result.Output)

// Multi-turn session
session, _ := client.CreateSession(ctx, cody.WithTitle("My task"))
client.Run(ctx, "create Flask app", cody.WithSession(session.ID))

// Streaming
ch, _ := client.Stream(ctx, "explain this code")
for chunk := range ch {
    fmt.Print(chunk.Content)
}
```

Zero dependencies, automatic retry, context cancellation. Full docs: [sdk/go/README.md](sdk/go/README.md).

## Tool Set (28)

| Category | Tools |
|----------|-------|
| File I/O | `read_file`, `write_file`, `edit_file`, `list_directory` |
| Search | `grep`, `glob`, `search_files`, `patch` |
| Shell | `exec_command` |
| Skills | `list_skills`, `read_skill` |
| Sub-Agent | `spawn_agent`, `get_agent_status`, `kill_agent` |
| MCP | `mcp_call`, `mcp_list_tools` |
| Web | `webfetch`, `websearch` |
| LSP | `lsp_diagnostics`, `lsp_definition`, `lsp_references`, `lsp_hover` |
| File History | `undo_file`, `redo_file`, `list_file_changes` |
| Task Mgmt | `todo_write`, `todo_read` |
| User I/O | `question` |

## Skills (Agent Skills Open Standard)

Skills follow the [Agent Skills open standard](https://agentskills.io/) — YAML frontmatter + Markdown, adopted by 26+ platforms (Claude Code, Codex CLI, Cursor, GitHub Copilot, etc.).

```markdown
---
name: git
description: Git version control operations. Use when working with git repositories.
metadata:
  author: cody
  version: "1.0"
---
# Git Operations
Instructions for the AI agent...
```

```
.cody/skills/          # Project skills (highest priority)
~/.cody/skills/        # User-global skills
{install}/skills/      # Built-in skills
```

**Progressive disclosure:** Only metadata (name + description) loads at startup; full instructions load on demand. `<available_skills>` XML auto-injected into system prompt.

**Built-in skills:** `git`, `github`, `docker`, `npm`, `python`, `rust`, `go`, `java`, `web`, `cicd`, `testing`

```bash
cody skills list                     # List available skills
cody skills show git                 # Show skill documentation
cody skills enable github            # Enable a skill
cody skills disable docker           # Disable a skill
```

## Configuration

### Project config (`.cody/config.json`)

```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "skills": {
    "enabled": ["git", "github", "docker"]
  },
  "mcp": {
    "servers": [
      {
        "name": "github",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "..."}
      }
    ]
  },
  "permissions": {
    "overrides": {"exec_command": "allow"}
  }
}
```

### Custom Model Provider (OpenAI-compatible APIs)

Use any OpenAI-compatible API (智谱 GLM, 阿里 DashScope, etc.) via environment variables:

```bash
# .env
CODY_MODEL=glm-4
CODY_MODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
CODY_MODEL_API_KEY=sk-your-key
```

Or via CLI flags:

```bash
cody run "写个单元测试" --model glm-4 --model-base-url https://open.bigmodel.cn/api/paas/v4/ --model-api-key sk-xxx
```

Or in `.cody/config.json` (API key should be set via env var for security):

```json
{
  "model": "qwen-coder-plus",
  "model_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
}
```

Priority: CLI flags > Environment variables > Config file.

### Aliyun Bailian Coding Plan (阿里云百炼)

Subscribe to [Coding Plan](https://www.aliyun.com/benefit/scene/codingplan) for bundled access to Qwen3.5, GLM-5, Kimi K2.5, MiniMax M2.5, etc.

Via environment variables:

```bash
# .env
CODY_MODEL=qwen3.5
CODY_CODING_PLAN_KEY=sk-sp-xxxxx
# Optional: use "anthropic" protocol for Claude-compatible models
# CODY_CODING_PLAN_PROTOCOL=anthropic
```

Via CLI flags:

```bash
cody run "写个排序算法" --model qwen3.5 --coding-plan-key sk-sp-xxx
cody run "写单元测试" --model qwen3.5 --coding-plan-key sk-sp-xxx --coding-plan-protocol anthropic
```

Via RPC Server request:

```json
{
  "prompt": "写一个排序算法",
  "model": "qwen3.5",
  "coding_plan_key": "sk-sp-xxxxx"
}
```

Supports two protocols:

- **OpenAI compatible** (default): `https://coding.dashscope.aliyuncs.com/v1`
- **Anthropic compatible**: `https://coding.dashscope.aliyuncs.com/apps/anthropic`

> Note: Coding Plan API Key (`sk-sp-xxxxx`) is different from regular DashScope API Key (`sk-xxxxx`). Do not mix them.

### Config CLI

```bash
cody config show                     # Show current configuration
cody config set model "anthropic:claude-sonnet-4-0"  # Set model
cody config set model_base_url "https://..."          # Set custom API URL
```

### Global config (`~/.cody/config.json`)

```json
{
  "default_model": "anthropic:claude-sonnet-4-0",
  "skills": {"enabled": ["git"]}
}
```

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Run tests (493 tests)
python3 -m pytest tests/ -v

# Lint
python3 -m ruff check cody/ tests/

# Format
python3 -m ruff format cody/ tests/
```

## Documentation

- [API Reference](docs/API.md) — RPC endpoints, WebSocket, error codes, auth
- [Go SDK](sdk/go/README.md) — Go client with zero dependencies
- [Architecture](docs/ARCHITECTURE.md) — System design, component diagram, data flows
- [Features & Roadmap](docs/FEATURES.md) — Full feature list, version history, competitive analysis
- [Contributing](CONTRIBUTING.md) — Code standards, test requirements, git workflow, onboarding guide

## License

MIT

## Credits

Built with [Pydantic AI](https://ai.pydantic.dev/), [FastAPI](https://fastapi.tiangolo.com/), [Textual](https://textual.textualize.io/), [Click](https://click.palletsprojects.com/), [Rich](https://rich.readthedocs.io/).
