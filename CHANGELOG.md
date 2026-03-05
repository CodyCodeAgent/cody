# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

---

## [1.7.3] - 2026-03-05

### Fixed
- **CI Trusted Publisher** — 修正 PyPI trusted publisher workflow 名称配置

---

## [1.7.2] - 2026-03-05

### Fixed
- **CI pytest-timeout** — dev 依赖补充 `pytest-timeout`，修复 CI `--timeout=60` 参数报错
- **CI 前端测试** — 移除不稳定的前端测试 job，保留 Python 测试矩阵

### Changed
- **Python 版本要求** — 最低版本从 3.9 提升至 3.10（支持 `X | None` 联合类型语法）
- **CI 测试矩阵** — 3.10 / 3.11 / 3.12 / 3.13

---

## [1.7.1] - 2026-03-05

### Added
- **SDK `run_stream()` 方法** — `stream()` 的别名，提供更直观的 API 命名
- **SDK `RunResult.thinking`** — 非流式模式下也可获取模型思考内容
- **SDK `StreamChunk` 增强字段** — `tool_name`、`args`（tool_call 事件）、`usage`（done 事件）
- **SDK Builder `.on()` 方法** — 在 Builder 链中直接注册事件处理器，自动启用 events
- **SDK `on()` 字符串支持** — `client.on("tool_call", handler)` 等效于 `client.on(EventType.TOOL_CALL, handler)`
- **SDK 自动 Session** — `run()` 自动创建 session，首次调用即返回 `session_id`，无需手动 `create_session()`
- **SDK 非流式工具事件** — 非流式 `run()` 完成后从 `tool_traces` 补发 `TOOL_CALL`/`TOOL_RESULT` 事件

### Fixed
- **SDK 模型覆盖 Bug** — `AsyncCodyClient()` 不传 model 时，SDK 默认值不再覆盖环境变量 `CODY_MODEL`
- **Web `estimate_tokens` TypeError** — 多模态消息（ImageUrl）不再导致 token 估算崩溃
- **Web AgentRunner 性能** — 按 workdir 缓存 AgentRunner（5 分钟 TTL），避免每次消息重建

### Changed
- **Web Stop 按钮移除** — pydantic-ai 无优雅停止机制，移除前端 Stop 按钮避免误导

---

## [1.7.0] - 2026-03-05

### Added
- **SDK 增强模块** (`cody/sdk/`) — Builder 模式、事件系统、指标收集、增强错误处理
  - `Cody()` Builder — 链式配置，`Cody().workdir("/path").model("...").build()`
  - `EventManager` — 事件钩子系统，支持同步/异步 handler
  - `MetricsCollector` — Token 使用、工具调用、会话级指标收集
  - 10 个细粒度错误类（CodyModelError、CodyToolError、CodyPermissionError 等）
  - 4 个示例文件（basic、streaming、events、tools）
  - 65 个 SDK 测试
- **依赖分层** — `pyproject.toml` 拆分为核心依赖 + 可选依赖组
  - `pip install cody-ai` — 只装核心（pydantic-ai, anthropic, pydantic, httpx）
  - `pip install cody-ai[cli]` — 加 CLI（click, rich）
  - `pip install cody-ai[tui]` — 加 TUI（textual）
  - `pip install cody-ai[web]` — 加 Web（fastapi, uvicorn）
  - `pip install cody-ai[all]` — 全部
- **Web 中间件测试** — 新增 `web/tests/test_middleware.py`（9 个测试覆盖认证、限流、审计）
- **CLI/TUI 补充测试** — CLI 新增 9 个测试（参数传递、流式渲染、会话恢复），TUI 新增 5 个测试（批量刷新、状态栏、命令处理）
- **WebSocket 鉴权** — WebSocket `/ws` 和 `/ws/chat` 端点现需认证 token（S3）
- **CLI/TUI 共享工具库** — 新增 `cody/shared.py`，提取 CLI/TUI 重复工具函数（R1）
- **ToolContext 依赖注入** — 新增 `core/deps.py:ToolContext`，统一工具直接调用上下文（R3）
- **可扩展命令黑名单** — `SecurityConfig.blocked_commands` 允许用户自定义禁用命令模式（S5）
- **Web 路由测试补充** — 新增 21 个 Web 路由测试覆盖 config/agent/audit/skills 端点（R9）
- **目录浏览路径限制** — `/api/directories` 限制在用户 home 目录内（R10）

### Changed

- **CLI/TUI 拆分为 Python 包** — `cody/cli.py`（830 行）拆为 `cody/cli/` 包（main.py + commands/ + rendering.py + utils.py），`cody/tui.py`（566 行）拆为 `cody/tui/` 包（app.py + widgets.py）。所有导入路径向后兼容。
- **SDK 合并** — `cody/sdk/` 成为唯一 SDK 实现，直接包装 core（单层），`cody/client.py` 变为向后兼容 re-export shim
  - 新增 `cody/sdk/types.py` — SDK 响应类型（RunResult、Usage、StreamChunk 等）
  - `cody/sdk/client.py` 重写 — 不再双层包装（sdk → client → core），改为直接包装 core
  - 所有导入路径向后兼容：`from cody import ...`、`from cody.client import ...`、`from cody.sdk import ...`
- **TUI 性能优化** — StreamBubble 改为 30fps 批量渲染 + 滚动节流
  - 工具参数显示截断（超 120 字符自动截断）
  - ToolResultEvent 显示摘要行（工具名 + 结果长度）
  - 长对话消息回收（超 200 条自动移除旧 widget）
- **CLI 工具参数截断** — 与 TUI 一致的 `_truncate_repr` 截断显示
- **Web 前端版本同步** — `web/package.json` 版本号从 1.3.0 → 1.6.0
- **pyproject.toml 描述更新** — 对齐框架定位
- **Web CORS 白名单可配置** — 支持 `CODY_CORS_ORIGINS` 环境变量覆盖（默认仍为 localhost 开发地址）
- **Web 后端异步化 SQLite** — 路由层使用 `asyncio.to_thread()` 包装阻塞式 ProjectStore/SessionStore 调用
- **Web 后端异常处理统一** — `projects.py`、`directories.py` 中的 `HTTPException` 统一改为 `raise_structured()`
- **Web 后端密钥遮蔽加强** — Config 端点 API Key 显示从部分展示改为全量遮蔽 `***`
- **WebSocket 指数退避重连** — 前端 WebSocket 断线重连从固定 2s 改为指数退避（2s → 60s 上限）
- **SDK 指标异常安全** — `MetricsCollector.end_run()` 移至 `finally` 块，异常时不丢失指标
- **前端删除确认** — Sidebar 删除项目前增加 `window.confirm()` 确认
- **Token 估算改进** — CJK 字符按 1.5 token 估算（原为 0.25）
- **MCP 启动失败清理** — `start_all()` 返回失败列表，失败时清理残留进程和 reader task
- **目录浏览安全** — 跳过符号链接，防止目录遍历
- **Config 缓存 TTL** — Web Backend 的 Config 缓存增加 60 秒 TTL，自动刷新（R7）
- **AuditEvent 枚举化** — `AuditEvent` 从普通类改为 `str, Enum`（O4）
- **API Key 占位改进** — 未设置 API Key 时使用空字符串代替 `"not-set"`（O2）
- **文件操作 UTF-8** — `FileHistory.undo()/redo()` 写入时指定 `encoding="utf-8"`（O3）
- **Refresh Token 权限校验** — `AuthManager.refresh()` 增加 scope 验证（R8）
- **client.py 导出清理** — 移除私有符号 `_event_to_chunk`/`_usage_from_result` 的 re-export（O8）

### Fixed
- **子代理循环依赖** — `sub_agent.py` 延迟导入处添加注释说明
- **run_sync 上下文压缩缺失** — `run_sync()` 现在与 `run()` 一致调用 `_compact_history_if_needed()`（S1）
- **HTML 解析器嵌套 skip 标签 bug** — `_HTMLToMarkdown` 将 `_skip` 布尔值改为 `_skip_depth` 计数器（S2）
- **exec_command 白名单绕过** — 管道/链式命令现在逐段检查白名单（S5）
- **CodyBuilder _permissions 默认值** — 改为 `field(default_factory=dict)` 避免共享可变对象（O6）

### Removed
- `python-dotenv` — 从依赖中移除（代码未使用）
- `pylint.yml` — 删除过时的 Pylint CI 工作流，统一使用 ruff（S4）
- **SDK apply_env()** — 移除环境变量自动覆盖配置的方法（R4）

### Refactored

- **CLI Skills 命令** — 使用 `SkillManager` 直接管理 Skills，不再经过 `AgentRunner`（R2）
- **CLI Chat REPL** — 单 event loop 重构，消除重复 `asyncio.run()` 调用（R6）
- **CI 工作流重写** — Python 版本矩阵（3.9-3.13）、PR 触发、Web 测试覆盖（S4）
- **前端 summarizeArgs 去重** — 提取到 `web/src/utils/summarizeArgs.ts`，ChatWindow 和 MessageBubble 共享
- **前端项目状态管理** — 新增 `useProjects` hook，HomePage 和 Sidebar 共享项目列表
- **ChatWindow 拆分** — 提取 `useStreamBuffer` hook 和 `StreamingBubble` 组件，主文件从 510 行缩减到 ~300 行
- **前端响应式布局** — `index.css` 添加 768px 断点移动端适配
- **文件历史持久化** — FileHistory 支持可选 SQLite 持久化（Web 模式启用）

---

## [1.6.0] - 2026-03-03

### Added
- **交互式配置向导** — 新增 `cody config setup` 命令，引导用户选择模型提供商、输入 API Key 等
  - 首次使用 `cody run`/`chat`/`tui` 时如果未配置会自动触发
  - `cody init` 完成后也会提示配置
- **Config.is_ready()** — 配置完整性检查方法，判断是否有足够的 API 凭证
- **Config.missing_fields()** — 返回缺失配置项的描述列表
- **model_api_key 持久化** — API Key 现在保存到配置文件，无需环境变量
- **model_api_key Anthropic 路径** — 配置了 `model_api_key` 但无 `model_base_url` 时，自动使用 Anthropic API
- **config show 脱敏** — `cody config show` 显示 API Key 时自动脱敏（如 `sk-ant...xyz`）
- **config set 扩展** — 支持设置 `enable_thinking`、`thinking_budget`

### Removed
- **claude_oauth_token** — 删除 OAuth 认证路径，统一使用 `model_api_key`
- **CLI --model-base-url / --model-api-key** — 从 `run`/`chat`/`tui` 命令删除，改用 `cody config setup` 配置
- **CLAUDE_OAUTH_TOKEN 环境变量** — 不再读取
- **ANTHROPIC_API_KEY 环境变量** — 不再隐式使用，统一走 `model_api_key`

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
