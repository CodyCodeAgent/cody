# Cody - Architecture Design

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Users / Callers                       │
│         (CLI / TUI / Clawdbot / CI-CD / Other Agents)       │
└──────┬──────────────┬──────────────┬────────────────────────┘
       │              │              │
  CLI (Click)    TUI (Textual)   RPC Server (FastAPI)
  cody/cli.py    cody/tui.py    cody/server.py
       │              │              │
       └──────────────┴──────────────┘
                      │
         ┌────────────▼────────────┐
         │    Python SDK           │
         │    cody/client.py       │
         │    (CodyClient /        │
         │     AsyncCodyClient)    │
         └────────────┬────────────┘
                      │ (or direct)
┌─────────────────────▼───────────────────────────────────────┐
│                     Cody Core Engine                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │          AgentRunner (core/runner.py)                  │  │
│  │  - Creates Pydantic AI Agent                          │  │
│  │  - Registers 30+ tools                                │  │
│  │  - Context compaction (auto)                          │  │
│  │  - Session-aware run methods                          │  │
│  │  - Assembles CodyDeps for dependency injection        │  │
│  └──────────┬────────────────────────────────────────────┘  │
│             │                                                │
│  ┌──────────▼────────────────────────────────────────────┐  │
│  │     Tool & Extension Layer                            │  │
│  │  ┌──────────┬───────────┬──────────┬──────────────┐  │  │
│  │  │ Built-in │ Skill     │ MCP      │ LSP          │  │  │
│  │  │ Tools    │ System    │ Client   │ Client       │  │  │
│  │  │          │           │          │              │  │  │
│  │  │ file ops │ .cody/    │ stdio    │ pyright      │  │  │
│  │  │ search   │ ~/.cody/  │ JSON-RPC │ tsserver     │  │  │
│  │  │ exec     │ builtin/  │          │ gopls        │  │  │
│  │  │ web      │ 11 skills │ github   │              │  │  │
│  │  │ todo     │           │ db, fs   │ diagnostics  │  │  │
│  │  │ question │           │ etc.     │ definition   │  │  │
│  │  │ undo/    │           │          │ references   │  │  │
│  │  │ redo     │           │          │ hover        │  │  │
│  │  └──────────┴───────────┴──────────┴──────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│             │                                                │
│  ┌──────────▼────────────────────────────────────────────┐  │
│  │     Infrastructure Layer                              │  │
│  │  ┌───────────┬───────────┬──────────┬─────────────┐  │  │
│  │  │ Sub-Agent │ Session   │ Context  │ Security    │  │  │
│  │  │ Manager   │ Store     │ Manager  │             │  │  │
│  │  │           │           │          │ Permissions │  │  │
│  │  │ spawn     │ SQLite    │ compact  │ Auth/OAuth  │  │  │
│  │  │ kill      │ sessions  │ chunk    │ Audit Log   │  │  │
│  │  │ wait      │ messages  │ select   │ Rate Limit  │  │  │
│  │  │ 4 types   │ history   │ tokens   │ FileHistory │  │  │
│  │  └───────────┴───────────┴──────────┴─────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────────────┐
│                  External Services                           │
│  - Anthropic / OpenAI / Google / DeepSeek APIs              │
│  - File System                                              │
│  - Shell / Subprocess                                       │
│  - MCP Servers (GitHub, DB, FS, etc.)                       │
│  - Language Servers (pyright, tsserver, gopls)               │
│  - DuckDuckGo (web search)                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. AgentRunner (`core/runner.py`)

The central orchestrator. Responsibilities:
- Create Pydantic AI `Agent` with all tools registered
- Assemble `CodyDeps` dataclass for dependency injection into tools
- Auto-compact message history when approaching token limits
- Provide `run()`, `run_stream()`, `run_sync()` execution methods
- Session-aware variants: `run_with_session()`, `run_stream_with_session()`
- Manage lifecycle of MCP and LSP clients

**CodyDeps carries:**
```
Config, workdir, SkillManager, MCPClient, SubAgentManager,
LSPClient, AuditLogger, PermissionManager, FileHistory, todo_list
```

### 2. Tool System (`core/tools.py`)

All tools share the signature `async def tool(ctx: RunContext[CodyDeps], ...) -> str`.

**30+ tools across 11 categories:**

| Category | Tools | Permission |
|----------|-------|------------|
| File I/O | read_file, write_file, edit_file, list_directory | read=allow, write=confirm |
| Search | grep, glob, search_files, patch | grep/glob=allow, patch=confirm |
| Shell | exec_command | confirm |
| Skills | list_skills, read_skill | allow |
| Sub-Agent | spawn_agent, get_agent_status, kill_agent | spawn/kill=confirm, status=allow |
| MCP | mcp_call, mcp_list_tools | call=confirm, list=allow |
| Web | webfetch, websearch | allow |
| LSP | lsp_diagnostics, lsp_definition, lsp_references, lsp_hover | allow |
| File History | undo_file, redo_file, list_file_changes | undo/redo=confirm, list=allow |
| Task Mgmt | todo_write, todo_read | allow |
| User I/O | question | allow |

**Security:** All mutating tools call `_check_permission(ctx, tool_name)` before execution. File tools call `_resolve_and_check(workdir, path)` for path traversal protection.

### 3. Skill System (`core/skill_manager.py`)

Three-tier priority loading:
1. `.cody/skills/` — project-level (highest)
2. `~/.cody/skills/` — user-level
3. `{install}/skills/` — built-in

Each skill is a directory with a `SKILL.md` doc. The AI discovers skills via `list_skills()` and reads documentation via `read_skill()`.

**Built-in skills (11):** git, github, docker, npm, python, rust, go, java, web, cicd, testing

### 4. Sub-Agent System (`core/sub_agent.py`)

`SubAgentManager` orchestrates concurrent child agents:
- 4 types: `code`, `research`, `test`, `generic` (each with different tool sets)
- Max concurrency: 5 (via `asyncio.Semaphore`)
- Default timeout: 300s per agent
- Lifecycle: spawn → running → completed/failed/killed/timeout

**Note:** `_execute()` uses delayed imports to break `runner → sub_agent → runner` circular dependency.

### 5. MCP Client (`core/mcp_client.py`)

Manages MCP server subprocesses via stdio JSON-RPC:
- `start_all()` / `stop_all()` — batch lifecycle management
- Tool discovery via `tools/list` JSON-RPC
- `call_tool(server/tool, params)` — proxied tool calls
- Process death detection with error recovery

### 6. LSP Client (`core/lsp_client.py`)

Manages language server processes with Content-Length framed JSON-RPC:
- Python: pyright
- TypeScript: typescript-language-server
- Go: gopls
- Capabilities: diagnostics, go-to-definition, find-references, hover

### 7. Context Management (`core/context.py`)

- `compact_messages(msgs, max_tokens)` — summarize old messages when approaching token limits
- `chunk_file(path, chunk_size, overlap)` — split large files into overlapping chunks
- `select_relevant_context(query, files, max_tokens)` — keyword scoring with token budget

Auto-compaction is wired into `AgentRunner.run()` and `run_stream()`.

### 8. Session System (`core/session.py`)

SQLite-backed persistence:
- `create_session()`, `get_session()`, `list_sessions()`, `delete_session()`
- `add_message(session_id, role, content)` — append to conversation history
- Default DB: `~/.cody/sessions.db`

### 9. Security Stack

| Component | Module | Purpose |
|-----------|--------|---------|
| Permissions | `core/permissions.py` | Per-tool allow/deny/confirm, enforced at tool call time |
| Auth | `core/auth.py` | API Key verification + HMAC-SHA256 token issuance/validation |
| Audit | `core/audit.py` | SQLite event log (tool_call, file_write, command_exec, etc.) |
| Rate Limit | `core/rate_limiter.py` | Sliding window per-key throttling |
| File History | `core/file_history.py` | Undo/redo stack for file modifications |
| Path Safety | `core/tools.py` | `_resolve_and_check()` prevents symlink/traversal escapes |
| Cmd Safety | `core/tools.py` | Dangerous command detection (rm -rf, dd, fork bomb) |

Server wires these as middleware: auth → rate_limit → audit.

---

## Data Flows

### CLI Mode

```
User Input → Click CLI (cli.py) → AgentRunner.run(prompt)
  → Pydantic AI Agent → Tool calls → File/Exec/Skill/MCP/LSP
  → Results → Agent → LLM → Final Output → Display
```

### TUI Mode

```
User Input → Textual App (tui.py) → AgentRunner.run_stream_with_session()
  → Pydantic AI Agent → Tool calls → ...
  → Stream chunks → TUI StreamBubble → Real-time display
  → Session auto-persisted to SQLite
```

### RPC Mode

```
HTTP POST /run → FastAPI (server.py) → AgentRunner.run_with_session()
  → ... → JSON Response {output, session_id, usage}

HTTP POST /run/stream → SSE stream
  → ... → data: {"type":"text","content":"..."} events

WS /ws → WebSocket bidirectional
  → {"type":"run"} → stream → {"type":"text"} events
  → {"type":"cancel"} → abort → {"type":"cancelled"}
```

### Sub-Agent Mode

```
Main Agent → spawn_agent("task", "research") tool call
  → SubAgentManager.spawn() → asyncio.create_task()
  → Child Agent runs independently with subset of tools
  → Main Agent polls via get_agent_status()
  → Results aggregated into main conversation
```

---

## Configuration System

### Load Order (later overrides earlier)

1. Built-in defaults (Pydantic model defaults)
2. Global config: `~/.cody/config.json`
3. Project config: `.cody/config.json`
4. CLI arguments / environment variables

### Key Config Models (`core/config.py`)

```
Config
├── model: str                    # "anthropic:claude-sonnet-4-0"
├── skills: SkillConfig           # enabled[], disabled[]
├── mcp: MCPConfig                # servers[]
├── permissions: PermissionsConfig # overrides{}, default_level
├── security: SecurityConfig      # allowed_commands[], restricted_paths[]
└── auth: AuthConfig              # type, token, api_key
```

---

## Dependency Direction

```
cli.py ──→
tui.py ──→  core/*  ←── server.py
             ↓
         pydantic-ai, sqlite3, httpx, etc.
```

**Rule:** `core/` must NEVER import from `cli.py`, `tui.py`, or `server.py`. All functionality lives in core; shells just expose it.

---

**Last updated:** 2026-02-25
