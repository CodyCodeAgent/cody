# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [1.3.0] - 2026-03-02

### Added
- **Web frontend** — React + TypeScript + Vite single-page application (`web/`)
  - Project wizard with directory browser, name/description fields
  - Real-time chat via WebSocket with streaming message display
  - Project sidebar with create/delete/navigate
  - Dark theme UI
  - 33 frontend tests (Vitest + Testing Library)
- **Web backend** — Unified FastAPI application (`web/backend/`, port 8000)
  - Serves both Web-specific (projects, chat) and RPC endpoints (run, tool, sessions, skills, agents, ws)
  - Own SQLite database (`~/.cody/web.db`) for project management (CRUD)
  - Imports core directly (no HTTP intermediary)
  - WebSocket `/ws/chat/{project_id}` endpoint for real-time chat relay
  - Directory browsing API (`GET /api/directories`)
  - 20 backend tests (pytest)
  - Dependency injection via FastAPI `Depends()` for clean testing
- **CODY.md project instructions** — Cody now reads `CODY.md` at the start of every session and injects its content into the system prompt, similar to Claude Code's `CLAUDE.md`.
  - Two-layer loading: `~/.cody/CODY.md` (global user-level) + `<workdir>/CODY.md` (project-level); both are optional and additive
  - Global instructions come first, project instructions appended after a `---` separator
  - `cody init` always (re-)generates `CODY.md` via AI analysis — shows "Created" on first run, "Updated" on subsequent runs; if `.cody/` already exists, scaffold is skipped but `CODY.md` is still regenerated; fails loudly on error (no silent fallback)
  - New module `cody/core/project_instructions.py` with `load_project_instructions()`, `generate_project_instructions()`, `CODY_MD_FILENAME`, `CODY_MD_TEMPLATE`
- **`read_file` encoding safety** — tool now reads with `encoding="utf-8", errors="replace"` instead of platform default, preventing `UnicodeDecodeError` on binary or non-UTF-8 files
- **Tool error auto-retry** — `ToolError` exceptions (e.g. `ToolInvalidParams` from `edit_file` when text is not found) are now converted to pydantic-ai `ModelRetry`, allowing the model to self-correct and retry (up to 2 retries per tool call) instead of breaking the entire agent run

### Changed
- **Architecture simplification** — eliminated `cody/server.py` (standalone RPC server)
  - All RPC endpoints merged into `web/backend/` as a unified FastAPI app
  - Web backend imports core directly (no HTTP SDK intermediary)
  - Single server on port 8000 replaces two servers (8000 + 5001)
- **Python SDK refactored** — `cody/client.py` is now an in-process wrapper around core
  - No HTTP, no server required — imports core directly
  - Same API surface (`AsyncCodyClient`, `CodyClient`, `RunResult`, `StreamChunk`, etc.)
  - Removed `CodyConnectionError`, `CodyTimeoutError`, retry logic (no longer needed)
- **Go SDK removed** — simplified project (use Python SDK or HTTP API instead)

### Architecture
- All shells (CLI, TUI, Web) import core directly — "thick engine, thin shells"
- Unified architecture: `React → Web Backend (port 8000, web.db) → Core Engine`
- Python SDK: `CodyClient → core/* (in-process, no HTTP)`

---

## [1.2.0] - 2026-03-01

### Added
- **Multi-workdir support (`allowed_roots`)** — File tools can now access directories beyond the primary `workdir`. Two distinct concepts:
  - `workdir` — execution anchor (config discovery, subprocess cwd, session tag, LSP root)
  - `allowed_roots` — access boundary (directories tools can read/write)
  - Configurable via `security.allowed_roots` in `.cody/config.json`, `--allow-root` CLI flag (run/chat/tui), and `allowed_roots` field in Server requests
  - Additive merging: config + CLI/request roots are combined; `workdir` is always implicitly allowed
  - Config entries must be absolute paths (relative paths raise `ValueError` at startup)
- **Tool execution spinner** — CLI and TUI now show animated progress indicator with elapsed time during tool execution, replacing the previous "stuck" behavior
- **Context compression notification** — New `CompactEvent` in stream events; CLI prints a yellow notification line, TUI shows a system bubble when context auto-compaction occurs
- **TUI slash command hints** — Status line shows matching commands with descriptions as user types `/` in the input field

### Changed
- `_resolve_and_check()` in `tools.py` now accepts `allowed_roots` parameter; error message updated to "outside all permitted directories"
- `AgentRunner.__init__` accepts optional `extra_roots: list[Path]` parameter
- `CodyDeps` gains `allowed_roots: list[Path]` field (defaults to `[]`, backward compatible)
- `SecurityConfig` gains `allowed_roots: list[str]` field (defaults to `[]`)
- `Config.apply_overrides()` gains `extra_roots` parameter (additive semantics)
- `_compact_history_if_needed` now returns `(history, CompactResult)` tuple instead of just history
- `StreamEvent` union type now includes `CompactEvent`

---

## [1.1.1] - 2026-02-28

### Changed
- **Declarative tool registry** — Tools organized into categorized lists (`FILE_TOOLS`, `SEARCH_TOOLS`, etc.) with `register_tools()` / `register_sub_agent_tools()` replacing 48 lines of individual `agent.tool()` calls
- **Typed tool exceptions** — New `ToolError` hierarchy (`ToolPermissionDenied`, `ToolPathDenied`, `ToolInvalidParams`) replacing generic `ValueError`/`PermissionError` with string matching in server error handlers
- **Server caching** — Config cached per-workdir (deep copy on access); SessionStore as global singleton; SkillManager always fresh from disk
- **Complete CodyDeps** — `/tool` endpoint and sub-agents now create full `CodyDeps` with audit_logger, permission_manager, file_history (previously missing)

## [1.1.0] - 2026-02-28

### Added
- **Thinking Mode** — `--thinking` / `--thinking-budget` flags for CLI (run/chat/tui), Server request params, env vars `CODY_ENABLE_THINKING` / `CODY_THINKING_BUDGET`
- **CodyResult** — Rich result model with `output`, `thinking`, `tool_traces`, `usage`; `ToolTrace` records every tool call
- **StreamEvent system** — 5 structured event types (`ThinkingEvent`, `TextDeltaEvent`, `ToolCallEvent`, `ToolResultEvent`, `DoneEvent`)
- `run_stream()` now uses pydantic-ai `run_stream_events()` API, yields structured events instead of raw strings

### Changed
- CLI `run` and `chat` commands switched from sync `run_sync()` to async streaming `run_stream()` with typewriter effect
- TUI consumes `StreamEvent`, uses `DoneEvent.result.all_messages()` for accurate message history
- Server SSE (`/run/stream`) and WebSocket (`/ws`) emit structured JSON events (thinking/tool_call/tool_result/text_delta/done)
- `_serialize_stream_event()` unifies SSE and WebSocket serialization

### Fixed
- TUI message history reconstruction bug — no longer manually rebuilds ModelRequest/ModelResponse pairs

## [1.0.1] - 2026-02-26

### Added
- **Agent Skills open standard** — YAML frontmatter + Markdown format, aligned with [agentskills.io](https://agentskills.io/) (26+ platforms)
- **Progressive disclosure** — Only YAML frontmatter (~50-100 tokens/skill) loaded at startup; full body on demand
- **Aliyun Bailian Coding Plan** — `--coding-plan-key` / `--coding-plan-protocol` for bundled model access (Qwen3.5, GLM-5, Kimi K2.5, etc.)
- **Claude OAuth token** authentication support

### Changed
- All 11 SKILL.md files migrated to YAML frontmatter format
- `SkillManager` rewritten with frontmatter parser (zero external deps), name validation, `to_prompt_xml()` for system prompt injection
- Plain Markdown files without frontmatter no longer loaded (breaking change)

## [1.0.0] - 2026-02-20

### Added
- **RPC Server** — FastAPI HTTP/WebSocket server with RESTful API (`/run`, `/run/stream`, `/tool`, `/skills`, `/sessions`, `/ws`, `/health`)
- **Python SDK** — `CodyClient` (sync) + `AsyncCodyClient` (async) with retry and exponential backoff
- **Go SDK** — Zero-dependency Go client with full API coverage, auto-retry, context cancellation
- **30+ AI Tools** — File I/O, search (grep/glob/patch), shell, sub-agents, MCP, web, LSP, file history, task management
- **11 Built-in Skills** — git, github, docker, npm, python, rust, go, java, web, cicd, testing
- **Sub-Agent System** — 4 types (code/research/test/generic), asyncio concurrency (max 5)
- **MCP Integration** — stdio JSON-RPC to external MCP servers (GitHub, databases, etc.)
- **LSP Intelligence** — Python (pyright), TypeScript (tsserver), Go (gopls) diagnostics, go-to-def, references, hover
- **CI/CD Templates** — GitHub Actions for AI code review, auto-fix, test generation
- **Session Persistence** — SQLite-backed multi-session management
- **Security** — Tool permissions, path traversal protection, dangerous command detection, audit logging, rate limiting, OAuth 2.0
- **Multi-Model** — Anthropic Claude, OpenAI GPT, Google Gemini, DeepSeek, GLM, Qwen, and any OpenAI-compatible API
- **CLI** — `cody run`, `cody chat`, `cody init`, `cody skills`
- **TUI** — Full-screen Textual terminal UI with streaming, session management, slash commands
- **Context Management** — Auto-compact conversations, smart file chunking
