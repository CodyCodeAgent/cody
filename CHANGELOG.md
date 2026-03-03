# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [1.6.0] - 2026-03-03

### Added
- **交互式配置向导** — 新增 `cody config setup` 命令，引导用户选择模型提供商、输入 API Key 等
  - 首次使用 `cody run`/`chat`/`tui` 时如果未配置会自动触发
  - `cody init` 完成后也会提示配置
- **Config.is_ready()** — 配置完整性检查方法，判断是否有足够的 API 凭证
- **Config.missing_fields()** — 返回缺失配置项的描述列表
- **model_api_key 持久化** — API Key 现在保存到配置文件，无需环境变量
- **model_api_key Anthropic 路径** — 配置了 `model_api_key` 但无 `model_base_url` 时，自动使用 Anthropic API（不再依赖 `ANTHROPIC_API_KEY` 环境变量）
- **config show 脱敏** — `cody config show` 显示 API Key 时自动脱敏（如 `sk-ant...xyz`）
- **config set 扩展** — 支持设置 `enable_thinking`、`thinking_budget`

### Removed
- **claude_oauth_token** — 删除 OAuth 认证路径，统一使用 `model_api_key`
- **CLI --model-base-url / --model-api-key** — 从 `run`/`chat`/`tui` 命令删除，改用 `cody config setup` 配置
- **CLAUDE_OAUTH_TOKEN 环境变量** — 不再读取

### Changed
- `Config.save()` 现在保存 `model_api_key` 到配置文件
- `model_resolver.py` 简化为 3 条路径：base_url → api_key(Anthropic) → 默认字符串
- 新增 `cody/core/setup.py` 提供配置向导的数据层

---

## [1.5.0] - 2026-03-03

### Added
- **Web 图片上传** — Web 前端支持多模态输入，用户可以粘贴截图或选择图片文件随消息一起发送
  - 支持 Ctrl+V 粘贴剪贴板图片、点击按钮选择文件（`image/*`）
  - 发送前预览已选图片，支持单独删除
  - 消息气泡中展示历史图片
  - 图片以 base64 存储在 SQLite 中，会话恢复时自动加载
- **多模态 Prompt 类型** — 新增 `cody/core/prompt.py`，定义 `ImageData`、`MultimodalPrompt`、`Prompt` 类型
  - `Prompt = Union[str, MultimodalPrompt]` — 类型安全的多模态提示，向后兼容纯文本
  - `prompt_text()` / `prompt_images()` — 类型安全的提取函数
  - 核心引擎 `AgentRunner` 通过 pydantic-ai `BinaryContent` 将图片传递给支持多模态的模型（如 Qwen3.5-plus）
- **Session 图片持久化** — `Message` 新增 `images` 字段，SQLite 自动迁移 `ALTER TABLE messages ADD COLUMN images`

### Changed
- `AgentRunner.run()` / `run_stream()` / `run_sync()` / `run_with_session()` / `run_stream_with_session()` 签名从 `prompt: str` 扩展为 `prompt: Prompt`（纯 `str` 仍然兼容）
- `CodyClient` / `AsyncCodyClient` SDK 签名同步扩展
- Web Backend `RunRequest` 新增 `images` 可选字段
- Web Backend 路由（chat、run、websocket）统一使用 `build_prompt()` 构造多模态提示
- `messages_to_history()` 支持重建带图片的多模态对话历史

---

## [1.4.0] - 2026-03-02

### Added
- **Streaming status indicators** — All three UIs (CLI, TUI, Web) now show real-time processing status with elapsed time during agent execution
  - **CLI**: "Thinking..." spinner at stream start, tool-specific spinners with elapsed time, "Completed in Xs" summary at end
  - **TUI**: Unified status line indicator cycling through "Thinking..." → "Running {tool}..." → "Generating..." with elapsed time
  - **Web**: Streaming status bar with pulse animation, smart status text, elapsed timer, and **Stop** button to cancel generation
- **Web Stop button** — Users can now manually stop a stuck or unwanted streaming response
- **Web idle timeout** — Streaming auto-stops after 120 seconds of no events, showing a timeout message
- **Web disconnect recovery** — If WebSocket disconnects during streaming, the UI resets gracefully with a "Connection lost" message instead of hanging forever
- **GFM Markdown** — Web frontend now renders GitHub Flavored Markdown (tables, strikethrough, task lists) via `remark-gfm`

### Changed
- **CLI spinner refactored** — `_tool_spinner` replaced with generic `_status_spinner` supporting custom labels and done messages
- **TUI tool spinner unified** — Replaced per-tool `_start_tool_spinner`/`_stop_tool_spinner` with unified `_start_processing`/`_set_processing_state`/`_stop_processing`

### Fixed
- **FileNotFoundError auto-retry** — `FileNotFoundError` now triggers `ModelRetry` (alongside `ToolError`), allowing the AI to self-correct file paths instead of crashing
- **Web streaming stuck** — Fixed bug where WebSocket disconnection during streaming left the UI in permanent "Thinking..." state

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
