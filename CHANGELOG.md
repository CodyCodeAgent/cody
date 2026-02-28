# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

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
