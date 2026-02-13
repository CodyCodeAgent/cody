# Cody

AI coding engine with RPC Server, dynamic skills, MCP integration, and LSP intelligence.

**Core philosophy: engine first, shell second.** CLI, TUI, and Server are thin shells over a shared core engine. The Server + SDK delivery model is our differentiator — let others embed AI coding capabilities into their own systems.

## Features

- **30+ AI Tools** — File ops, search (grep/glob/patch), shell commands, undo/redo, task management, structured questions
- **5 Built-in Skills** — git, github, docker, npm, python — AI reads SKILL.md to learn usage
- **RPC Server + SDK** — FastAPI HTTP/WebSocket server, Python SDK (sync + async), embeddable into any system
- **MCP Integration** — Connect to external MCP servers (GitHub, databases, etc.) via stdio JSON-RPC
- **LSP Intelligence** — Python (pyright), TypeScript (tsserver), Go (gopls) — diagnostics, go-to-definition, references, hover
- **Sub-Agent System** — Spawn specialized agents (code/research/test) with asyncio concurrency
- **Context Management** — Auto-compact conversations approaching token limits, smart file chunking
- **Security** — Tool-level permissions (allow/deny/confirm), path traversal protection, dangerous command detection, audit logging, rate limiting, OAuth 2.0
- **Session Persistence** — SQLite-backed multi-session management with history
- **Multi-Model** — Anthropic Claude, OpenAI GPT, Google Gemini, DeepSeek, and more via Pydantic AI

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
cody "create a FastAPI hello world app"

# Interactive chat
cody chat

# Continue previous conversation
cody --continue "add tests for the API"

# Full-screen TUI
cody tui
```

## Four Modes of Operation

### CLI

```bash
cody "refactor auth.py"              # One-shot task
cody chat                            # Interactive REPL
cody --model opus "complex task"     # Specify model
cody --continue "keep going"         # Resume last session
cody --session abc123 "next step"    # Resume specific session
```

### TUI (Textual)

```bash
cody tui                             # Full-screen terminal UI
cody tui --continue                  # Resume last session
cody tui --session <id>              # Resume specific session
```

Features: streaming output, multi-session management, slash commands (/help, /new, /sessions, /clear), keyboard shortcuts (Ctrl+N, Ctrl+C, Ctrl+Q).

### RPC Server

```bash
cody-server                          # Default 0.0.0.0:8000
cody-server --port 9000              # Custom port
```

Endpoints: `POST /run`, `POST /run/stream` (SSE), `POST /tool`, `GET /skills`, `GET /sessions`, `WS /ws`, `GET /audit`, `GET /health`. Full docs: [docs/API.md](docs/API.md).

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

## Tool Set (30+)

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

## Skills

Skills are SKILL.md documents that teach the AI how to use tools and CLIs.

```
.cody/skills/          # Project skills (highest priority)
~/.cody/skills/        # User-global skills
{install}/skills/      # Built-in skills
```

**Built-in skills:** `git`, `github`, `docker`, `npm`, `python`

```bash
cody skills list                     # List available skills
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

# Run tests (418 tests)
python3 -m pytest tests/ -v

# Lint
python3 -m ruff check cody/ tests/

# Format
python3 -m ruff format cody/ tests/
```

## Documentation

- [API Reference](docs/API.md) — RPC endpoints, WebSocket, error codes, auth
- [Architecture](docs/ARCHITECTURE.md) — System design, component diagram, data flows
- [Features & Roadmap](docs/FEATURES.md) — Full feature list, version history, competitive analysis
- [Handoff Guide](docs/HANDOFF.md) — For developers joining the project
- [Contributing](CONTRIBUTING.md) — Code standards, test requirements, git workflow

## License

MIT

## Credits

Built with [Pydantic AI](https://ai.pydantic.dev/), [FastAPI](https://fastapi.tiangolo.com/), [Textual](https://textual.textualize.io/), [Click](https://click.palletsprojects.com/), [Rich](https://rich.readthedocs.io/).
