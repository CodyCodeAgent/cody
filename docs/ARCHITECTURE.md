# Cody — Architecture Design

## Open-source AI Coding Agent Framework

Cody's architecture follows a **framework + reference implementations** pattern. The `core/` package is a reusable AI agent framework — it owns all logic, tools, and orchestration. CLI, TUI, Web Backend, and Python SDK are four independent consumers that import core directly, each demonstrating a different integration surface (command-line, terminal UI, HTTP/WebSocket, programmatic).

**Why this structure?** By keeping every capability inside `core/`, anyone can build a new integration (IDE plugin, CI bot, Slack app, custom agent) without duplicating logic. The four built-in consumers serve as reference implementations and cover the most common use cases.

## 系统总览

```
┌────────────────────────────────────────────────────────────────┐
│                         Users / Callers                         │
│     (CLI / TUI / Web / SDK consumers / CI-CD / Other Agents)   │
└──┬──────────────┬──────────────┬──────────────┬────────────────┘
   │              │              │              │
  CLI           TUI        Web Frontend    Python SDK
  (Click)       (Textual)  (React+Vite)   (in-process)
  cody/cli/    cody/tui/   web/src/     cody/sdk/
   │              │              │              │
   │              │     Unified Web Backend     │
   │              │     (FastAPI:8000)           │
   │              │     web/backend/             │
   │              │     (Web + RPC endpoints)    │
   │              │     ↕ web.db                 │
   │              │              │              │
   │  (direct)    │  (direct)    │  (direct)    │  (direct)
   │              │              │              │
┌──▼──────────────▼──────────────▼──────────────▼────────────────┐
│                     Cody Core — Agent Framework                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │          CodyRuntime → AgentRunner executor                │  │
│  │  - Creates Pydantic AI Agent                              │  │
│  │  - Registers 28 core + 2 MCP tools                                     │  │
│  │  - Context compaction (auto)                              │  │
│  │  - Session-aware run methods                              │  │
│  │  - Assembles CodyDeps for dependency injection            │  │
│  └──────────┬────────────────────────────────────────────────┘  │
│             │                                                    │
│  ┌──────────▼────────────────────────────────────────────────┐  │
│  │     Tool & Extension Layer                                │  │
│  │  ┌──────────┬───────────┬──────────┬──────────────┐      │  │
│  │  │ Built-in │ Skill     │ MCP      │ LSP          │      │  │
│  │  │ Tools    │ System    │ Client   │ Client       │      │  │
│  │  │          │           │          │              │      │  │
│  │  │ file ops │ .cody/    │ stdio+   │ pyright      │      │  │
│  │  │ search   │ ~/.cody/  │ http     │ tsserver     │      │  │
│  │  │ exec     │ custom    │ JSON-RPC │ gopls        │      │  │
│  │  │ web      │ skills    │ github   │              │      │  │
│  │  │ todo     │           │ feishu   │ diagnostics  │      │  │
│  │  │ question │           │ etc.     │ definition   │      │  │
│  │  │ undo/    │           │          │ references   │      │  │
│  │  │ redo     │           │          │ hover        │      │  │
│  │  │ memory   │           │          │              │      │  │
│  │  └──────────┴───────────┴──────────┴──────────────┘      │  │
│  └───────────────────────────────────────────────────────────┘  │
│             │                                                    │
│  ┌──────────▼────────────────────────────────────────────────┐  │
│  │     Infrastructure Layer                                  │  │
│  │  ┌───────────┬───────────┬──────────┬─────────────┐      │  │
│  │  │ Sub-Agent │ Session   │ Context  │ Security    │      │  │
│  │  │ Manager   │ Store     │ Manager  │             │      │  │
│  │  │           │           │          │ Permissions │      │  │
│  │  │ spawn     │ SQLite    │ compact  │ Audit Log   │      │  │
│  │  │ kill      │ sessions  │ chunk    │ Rate Limit  │      │  │
│  │  │ wait      │ messages  │ select   │ FileHistory │      │  │
│  │  │ 4 types   │ history   │ tokens   │ CircuitBkr  │      │  │
│  │  │           │           │          │ ProjMemory  │      │  │
│  │  └───────────┴───────────┴──────────┴─────────────┘      │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
              │
┌─────────────▼────────────────────────────────────────────────────┐
│                  External Services                                │
│  - Anthropic / OpenAI / Google / DeepSeek APIs                   │
│  - File System                                                   │
│  - Shell / Subprocess                                            │
│  - MCP Servers (GitHub, DB, FS, etc.)                            │
│  - Language Servers (pyright, tsserver, gopls)                    │
│  - DuckDuckGo (web search)                                       │
└──────────────────────────────────────────────────────────────────┘
```

All four consumers — CLI, TUI, Web Backend, Python SDK — import `core/` directly as an in-process library. There is no intermediary layer between any consumer and the framework.

---

## Framework Core 组件

### 1. Canonical Runtime 与 AgentRunner

`CodyRuntime` 是长期运行和工作流的高层入口。它拥有 Run 生命周期，并将同一组
Run、Trace、Checkpoint、Artifact、Approval 与 Audit stores 交给工作流服务。
`AgentRunner` 是 Agent 类型 workflow node 的执行器。

```text
CodyRuntime
  → WorkflowRunManager
    → AsyncWorkflowExecutor
      → AgentRunner.run_events()
        → canonical RunEvent + shared stores
```

`AgentRunner.run_events()` 是 canonical 实时事件接口。兼容的 `run_stream()` 从 live
`RunEvent` 中还原旧 `StreamEvent`，因此 CLI/TUI/Web/现有 SDK 可以渐进迁移。Agent
嵌入工作流时使用 step event scope，结束事件为 `model.completed`；只有 Runtime
拥有的父 Run 才写入 `run.completed`。

`CodyRuntime.start()` 返回 `RuntimeRun`，支持 `events()`、`result()`、`cancel()`。
workflow 定义随 RunRecord 持久化；waiting approval 被批准后，新的 Runtime 实例可
通过 `resume(run_id)` 从最新 checkpoint 继续执行。

失败/取消 Run 可以通过 `retry()` 从最新或指定 checkpoint 重试；`fork()` 从任意
历史 checkpoint 创建带 `parent_run_id` 和 `parent_checkpoint_id` 的新 Run。Runtime
Tool Registry 使用持久化 Artifact receipt 实现 retry-safe 工具节点，同一 Run 内
回退 checkpoint 不会重复执行已完成的副作用。

包含 `parallel` / `join` / `fallback` / `nested_workflow` 的图由
`AsyncWorkflowScheduler` 执行。调度器并发运行当前 ready batch，在 batch 边界保存
安全 checkpoint，支持 per-node timeout/retry、全局 step/concurrency 上限和运行中
取消。并行输出按 node id 确定性合并；同一 key 的不同值默认报错，可显式选择
`last_write_wins` 或 `namespace` policy。

`agent_team` workflow node 由 `AsyncMultiAgentCoordinator` 执行。无依赖任务并发，
依赖任务在后续轮次启动；任务可声明 capability、preferred/fallback agent、timeout
和 max attempts。每个成功任务保存独立 Artifact，并以 `agent_outputs[task_id]`
隔离输出，避免 specialist 之间出现隐式覆盖。

`quality_gate` workflow node 使用 `AsyncQualityGateRunner` 并发计算指标。每次 decision
写入 canonical event、checkpoint 和 REVIEW Artifact。失败 decision 可以通过
fallback edge 进入 repair node；repair edge 使用 `allow_revisit` 返回 gate，直到通过
或耗尽 `max_repairs`。全局 `max_steps` 提供第二层循环保护。

### 1b. AgentRunner (`core/runner.py`)

The central orchestrator. Responsibilities:
- Create Pydantic AI `Agent` with all tools registered
- Assemble `CodyDeps` dataclass for dependency injection into tools
- Auto-compact message history when approaching token limits
- Provide canonical `run_events()` and compatible `run()` / `run_stream()` / `run_sync()` methods
- Session-aware variants: `run_with_session()`, `run_stream_with_session()`
- Multimodal support: `_to_pydantic_prompt()` converts `Prompt` to pydantic-ai format (`str` or `[text, BinaryContent, ...]`)
- Manage lifecycle of MCP and LSP clients
- Optional thinking mode (`enable_thinking` + `thinking_budget` in config)

**StreamEvent system:** `run_stream()` yields structured `StreamEvent` objects (not raw text):
```
SessionStartEvent       — session ID (always first event in run_stream_with_session, v1.11.0+)
ThinkingEvent           — incremental thinking content (delta)
TextDeltaEvent          — incremental text output (delta)
ToolCallEvent           — tool call initiated (tool_name, args, tool_call_id)
ToolResultEvent         — tool call result (tool_name, result)
DoneEvent               — stream complete, contains full CodyResult
CancelledEvent          — run cancelled via cancel_event (v1.10.3+)
CircuitBreakerEvent     — run terminated by circuit breaker (reason, tokens, cost)
InteractionRequestEvent — human input needed (question/confirm/feedback)
UserInputReceivedEvent  — user proactively sent a message (injected at next node boundary)
```
`run_stream()` accepts an optional `cancel_event: asyncio.Event` parameter. When set, the stream yields a `CancelledEvent` and stops. Core provides all data; consumers (CLI/TUI/Web/SDK) decide rendering.

**SDK StreamChunk types:** The SDK layer (`sdk/types.py`) converts core `StreamEvent` to `StreamChunk` objects via `_event_to_chunk()`. `StreamChunk` is a base dataclass; 12 typed subclasses (`TextDeltaChunk`, `ToolCallChunk`, `DoneChunk`, etc.) enable `isinstance()` narrowing for type-safe consumers. Old `chunk.type == "..."` code remains compatible.

**CodyResult:** Rich result model returned by `run()` / `run_sync()` and via `DoneEvent`:
```
CodyResult
├── output: str            # final text output
├── thinking: str | None   # concatenated thinking content
├── tool_traces: list      # all tool calls with args and results
├── metadata: TaskMetadata | None  # structured output (summary, confidence, issues, next_steps)
└── _raw_result            # pydantic-ai AgentRunResult (for all_messages, usage)
```

**CodyDeps carries:**

```text
Config, workdir, SkillManager, MCPClient, SubAgentManager,
LSPClient, AuditLogger, PermissionManager, FileHistory, todo_list,
ProjectMemoryStore, interaction_handler, before_tool_hooks, after_tool_hooks
```

**ToolContext** (`core/deps.py`): Lightweight context for direct tool invocation outside of agent runs (e.g., SDK `tool()` calls, Web `/tool` endpoint). Wraps `CodyDeps` in a `RunContext`-compatible interface.

**Shared utilities** (`cody/shared.py`): CLI and TUI share common helper functions (spinner frames, elapsed formatting, session display, config path resolution) via this module, avoiding code duplication.

### 2. Tool System (`core/tools/`)

All tools share the signature `async def tool(ctx: RunContext[CodyDeps], ...) -> str`.

**Modular package structure:** The tool system is organized as a Python package (`core/tools/`) with 14 submodules by category:

```
core/tools/
├── __init__.py      — re-exports all tools, lists, and registration functions (backward compatible)
├── _base.py         — shared helpers: _check_permission, _resolve_and_check, _with_model_retry
├── _file_filter.py  — _is_binary, _parse_gitignore, _iter_files, constants
├── file_ops.py      — read_file, write_file, edit_file, list_directory
├── search.py        — grep, glob, patch, search_files
├── command.py       — exec_command
├── skills.py        — list_skills, read_skill
├── agents.py        — spawn_agent, get_agent_status, kill_agent, resume_agent
├── mcp.py           — mcp_list_tools, mcp_call
├── web.py           — webfetch, websearch
├── lsp.py           — lsp_diagnostics, lsp_definition, lsp_references, lsp_hover
├── history.py       — undo_file, redo_file, list_file_changes
├── todo.py          — todo_write, todo_read
├── user.py          — question
├── memory.py        — save_memory
└── registry.py      — *_TOOLS lists, CORE_TOOLS, register_tools(), register_sub_agent_tools()
```

**Declarative tool registry** (in `registry.py`):
```
FILE_TOOLS      — read_file, write_file, edit_file, list_directory
SEARCH_TOOLS    — grep, glob, patch, search_files
COMMAND_TOOLS   — exec_command
SKILL_TOOLS     — list_skills, read_skill
SUB_AGENT_TOOLS — spawn_agent, get_agent_status, kill_agent, resume_agent
MCP_TOOLS       — mcp_call, mcp_list_tools
WEB_TOOLS       — webfetch, websearch
LSP_TOOLS       — lsp_diagnostics, lsp_definition, lsp_references, lsp_hover
FILE_HISTORY_TOOLS — undo_file, redo_file, list_file_changes
TODO_TOOLS      — todo_write, todo_read
USER_TOOLS      — question
MEMORY_TOOLS    — save_memory

CORE_TOOLS = FILE_TOOLS + SEARCH_TOOLS + ... + MEMORY_TOOLS  (all except MCP)
```

**Registration functions:**
- `register_tools(agent, include_mcp=False, custom_tools=None, include_tools=None, exclude_tools=None)` — used by `AgentRunner` to register all tools. Optional `custom_tools` list appends user-defined async tool functions. `include_tools`/`exclude_tools` filter per-run tool sets.
- `register_sub_agent_tools(agent, agent_type)` — registers a subset based on agent type (`code`, `research`, `test`, `generic`)

**Backward compatibility:** `from cody.core.tools import read_file` and `from cody.core import tools; tools.read_file` both work unchanged.

**30 tools (28 core + 2 MCP) across 12 categories:**

| Category | Tools | Permission |
|----------|-------|------------|
| File I/O | read_file, write_file, edit_file, list_directory | read=allow, write=confirm |
| Search | grep, glob, search_files, patch | grep/glob=allow, patch=confirm |
| Shell | exec_command | confirm |
| Skills | list_skills, read_skill | allow |
| Sub-Agent | spawn_agent, get_agent_status, kill_agent, resume_agent | spawn/kill/resume=confirm, status=allow |
| MCP | mcp_call, mcp_list_tools | call=confirm, list=allow |
| Web | webfetch, websearch | allow |
| LSP | lsp_diagnostics, lsp_definition, lsp_references, lsp_hover | allow |
| File History | undo_file, redo_file, list_file_changes | undo/redo=confirm, list=allow |
| Task Mgmt | todo_write, todo_read | allow |
| User I/O | question | allow |
| Memory | save_memory | allow |

**Tool middleware (step hooks):** SDK consumers can register `before_tool` and `after_tool` hooks via the builder. Hooks are stored in `CodyDeps.before_tool_hooks` / `after_tool_hooks` and invoked inside `_with_model_retry()` — the wrapper that wraps every tool. `before_tool(tool_name, args) → args | None` can modify args or reject a call (None → `ModelRetry`); `after_tool(tool_name, args, result) → result` can transform the output. Multiple hooks chain in registration order.

**Typed exceptions:** Tool errors use a typed hierarchy (`ToolError` base, with `ToolPermissionDenied`, `ToolPathDenied`, `ToolInvalidParams`) defined in `core/errors.py`. The server catches these by type instead of string-matching, mapping them to correct HTTP status codes (403/400/500).

**Security:** All mutating tools call `_check_permission(ctx, tool_name)` before execution. File tools call `_resolve_and_check(workdir, path)` for path traversal protection.

### 3. Skill System (`core/skill_manager.py`) — Agent Skills Open Standard

Implements the [Agent Skills open standard](https://agentskills.io/) (adopted by 26+ platforms including Claude Code, Codex CLI, Cursor, GitHub Copilot).

**SKILL.md format:** YAML frontmatter (`name`, `description`, optional `license`/`compatibility`/`metadata`/`allowed-tools`) + Markdown body.

Two-tier priority loading:
1. `.cody/skills/` — project-level (highest)
2. `~/.cody/skills/` — user-level

> v1.11.0+: Built-in skills removed. Users create custom skills per project. Skill infrastructure (SkillManager, progressive loading, system prompt injection) unchanged.

**Progressive disclosure:** Startup parses only YAML frontmatter (~50-100 tokens/skill). `skill.instructions` loads the full body on demand. `to_prompt_xml()` generates `<available_skills>` XML injected into the system prompt for model-driven skill discovery.

### 4. Sub-Agent System (`core/sub_agent.py`)

`SubAgentManager` orchestrates concurrent child agents:
- 4 types: `code`, `research`, `test`, `generic` (each with different tool sets)
- Max concurrency: 5 (via `asyncio.Semaphore`)
- Default timeout: 300s per agent
- Lifecycle: spawn → running → completed/failed/killed/timeout
- **Recoverable:** `resume(agent_id)` re-spawns a completed/failed/timed-out agent with the original task + previous output/error as context, so the model continues where it left off. `SubAgentResult` stores `task` and `agent_type` for resume context.

**Note:** `_execute()` uses delayed imports to break `runner → sub_agent → runner` circular dependency.

### 4b. Circuit Breaker (`core/runner.py`)

Prevents runaway agent execution. Three trigger conditions:
- **Token limit** — cumulative `total_tokens` exceeds `max_tokens` (default 200,000)
- **Cost limit** — estimated cost exceeds `max_cost_usd` (default $5.0)
- **Loop detection** — consecutive N tool results have SequenceMatcher similarity ≥ threshold (default 0.9)

Configured via `CircuitBreakerConfig` in `core/config.py`. Checked after each `CallToolsNode` in `run_stream()` and after `run()`/`run_sync()`.

### 4c. Interaction Layer (`core/interaction.py`)

Unified human-in-the-loop mechanism:
- `InteractionRequest` — AI asks for input (kind: `question`/`confirm`/`feedback`)
- `InteractionResponse` — human replies (action: `approve`/`reject`/`revise`/`answer`)
- Wired via `CodyDeps.interaction_handler` callback (async callable)
- `_build_stream_interaction_handler()` creates a handler that pushes events to a side queue and awaits a Future
- `submit_interaction()` resolves the pending Future

### 4d. Proactive User Input (`core/user_input.py`)

Users can send messages without the AI asking:
- `UserInputQueue` — async queue for unsolicited messages
- `inject_user_input(msg)` — enqueue from any consumer (SDK/Web/CLI)
- Drained at each `CallToolsNode` boundary in `run_stream()`
- Injected via `CallToolsNode.user_prompt` — pydantic-ai appends it as a `UserPromptPart` after tool results

### 4e. Project Memory (`core/memory.py`)

Cross-session knowledge store per project:
- Storage: `~/.cody/memory/<project_hash>/` with one JSON file per category
- Categories: `conventions`, `patterns`, `issues`, `decisions` (max 50 entries each)
- `ProjectMemoryStore.get_memory_for_prompt()` formats entries for system prompt injection
- `save_memory` tool lets the AI proactively persist learnings
- Low-confidence entries (< 0.3) filtered from prompt injection

### 5. MCP Client (`core/mcp_client.py`)

Manages MCP server connections via two transport modes:

**stdio transport** (local subprocess, default):

- Spawns child processes, communicates via stdin/stdout JSON-RPC
- Process death detection with error recovery

**HTTP transport** (remote endpoint, v1.9.0+):

- Connects to remote MCP servers via `httpx.AsyncClient` JSON-RPC over HTTP POST
- Custom headers support (e.g. authentication tokens)
- Suitable for cloud-hosted MCP servers (Feishu/Lark, etc.)

**Shared API** (both transports):

- `start_all()` / `stop_all()` — batch lifecycle management
- Tool discovery via `tools/list` JSON-RPC
- `call_tool(server/tool, params)` — proxied tool calls
- `list_tools()` / `get_tool()` — unified across stdio and HTTP servers
- `running_servers` — includes both stdio and HTTP server names

### 6. LSP Client (`core/lsp_client.py`)

Manages language server processes with Content-Length framed JSON-RPC:
- Python: pyright
- TypeScript: typescript-language-server
- Go: gopls
- Capabilities: diagnostics, go-to-definition, find-references, hover

### 7. Context Management (`core/context.py`)

Two-phase context reduction strategy (inspired by OpenCode):

1. **Selective Pruning** (`prune_tool_outputs`) — replaces old large tool/assistant outputs with lightweight `[output pruned at <ts>]` markers while preserving conversation structure. Configurable protection window for recent messages and minimum-saving thresholds.
2. **Full Compaction** (`compact_messages` / `compact_messages_llm`) — summarizes old messages when pruning alone is insufficient. Supports truncation-based (fast) and LLM-based (semantic) modes.

Additional utilities:
- `chunk_file(path, chunk_size, overlap)` — split large files into overlapping chunks
- `select_relevant_context(query, files, max_tokens)` — keyword scoring with token budget

Both phases are wired into `AgentRunner.run()` and `run_stream()` — pruning runs first, full compaction only if still over threshold.

### 8. Prompt Types (`core/prompt.py`)

Multimodal prompt type system:
- `ImageData` — single image (base64 data, media_type, optional filename) with `to_dict()`/`from_dict()` serialization
- `MultimodalPrompt` — text + images list
- `Prompt = Union[str, MultimodalPrompt]` — backward-compatible type alias
- `prompt_text()` / `prompt_images()` — type-safe extraction helpers

### 9. Session System (`core/session.py`)

SQLite-backed persistence (default implementation):
- `create_session()`, `get_session()`, `list_sessions()`, `delete_session()`
- `add_message(session_id, role, content, images)` — append to conversation history (images stored as JSON in SQLite)
- Auto-migration: `ALTER TABLE messages ADD COLUMN images` on first use
- Default DB: `~/.cody/sessions.db`

**Storage abstraction** (`core/storage.py`): Defines `SessionStoreProtocol`, `AuditLoggerProtocol`, `FileHistoryProtocol` as `runtime_checkable` Protocol interfaces. Default SQLite implementations satisfy these protocols automatically. SDK consumers can inject custom implementations (PostgreSQL, DynamoDB, etc.) via builder methods `.session_store()`, `.audit_logger()`, `.file_history()`.

### 10. Security Stack

| Component | Module | Purpose |
|-----------|--------|---------|
| Permissions | `core/permissions.py` | Per-tool allow/deny/confirm, enforced at tool call time |
| Auth | `core/auth.py` | API Key verification + HMAC-SHA256 token issuance/validation |
| Audit | `core/audit.py` | SQLite event log (tool_call, file_write, command_exec, etc.) |
| Rate Limit | `core/rate_limiter.py` | Sliding window per-key throttling |
| File History | `core/file_history.py` | Undo/redo stack for file modifications |
| Path Safety | `core/tools/_base.py` | `_resolve_and_check()` prevents symlink/traversal escapes |
| Cmd Safety | `core/tools/command.py` | Dangerous command detection (rm -rf, dd, fork bomb) |

Web Backend (`web/backend/middleware.py`) wires these as middleware: auth → rate_limit → audit.

---

## Reference Implementations（参考实现）

The four consumers demonstrate different ways to build on the core framework:

| Consumer | Module | Integration Pattern |
|----------|--------|---------------------|
| **CLI** | `cody/cli/` | Click commands → `AsyncCodyClient` (SDK) → `AgentRunner.run_stream()` → print events to terminal |
| **TUI** | `cody/tui/` | Textual app → `AsyncCodyClient` (SDK) → `AgentRunner.run_stream()` → render events in TUI widgets |
| **Web Backend** | `web/backend/` | FastAPI + `Depends()` injection → `AgentRunner.run_with_session()` → JSON/SSE/WebSocket responses |
| **Python SDK** | `cody/sdk/` | `CodyClient` / `AsyncCodyClient` → wraps core with Builder pattern + typed results |

Each consumer adds its own concerns (CLI adds argument parsing, TUI adds widget rendering, Web adds HTTP auth/middleware, SDK adds Builder API) while delegating all agent logic to core.

---

## Data Flows

### CLI Mode

```
User Input → Click CLI (cli/) → AgentRunner.run_stream(prompt)
  → Pydantic AI run_stream_events() → StreamEvent objects
  → ThinkingEvent → dim text
  → ToolCallEvent → "→ tool(args)"
  → TextDeltaEvent → streaming text output
  → DoneEvent → usage stats
```

### TUI Mode

```
User Input → Textual App (tui/) → AgentRunner.run_stream()
  → StreamEvent objects → TUI StreamBubble
  → TextDeltaEvent → real-time text display
  → ToolCallEvent → tool call indicator
  → DoneEvent → update message history + persist to SQLite
```

### HTTP/WS Mode (via Web Backend)

```
HTTP POST /run → FastAPI (web/backend/) → AgentRunner.run_with_session()
  → ... → JSON Response {output, thinking, tool_traces, session_id, usage}

HTTP POST /run/stream → SSE stream (structured events)
  → data: {"type":"thinking","content":"..."}
  → data: {"type":"tool_call","tool_name":"...","args":{...}}
  → data: {"type":"tool_result","tool_name":"...","result":"..."}
  → data: {"type":"text_delta","content":"..."}
  → data: {"type":"done","output":"...","thinking":"...","tool_traces":[...]}

WS /ws → WebSocket bidirectional (same event types as SSE)
  → {"type":"run"} → stream → structured events
  → {"type":"user_input","content":"..."} → inject into agent queue
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
├── model: str                    # "claude-sonnet-4-0"
├── skills: SkillConfig           # enabled[], disabled[]
├── mcp: MCPConfig                # servers[]
├── permissions: PermissionsConfig # overrides{}, default_level
├── security: SecurityConfig      # allowed_commands[], restricted_paths[]
├── sandbox: SandboxConfig        # backend, filesystem/network/resource policy
└── auth: AuthConfig              # type, token, api_key
```

### Sandbox execution boundary

All OS process execution crosses `SandboxHandle`: shell tools, quality gates,
stdio MCP servers, language servers, and commands launched by sub-agents share
the Run sandbox. Python hooks, model providers, and Runtime plugins are trusted
host extensions; they are not untrusted guest code.

`SandboxManager` selects one backend behind a stable contract:

- `seatbelt` on macOS and `bubblewrap` on Linux for hardened local execution;
- `docker`/`podman` for service deployments and resource quotas;
- `RemoteSandboxBackend` for provider adapters (microVM, Kubernetes, or hosted
  sandbox services);
- `local-policy` only as an explicit compatibility backend. It is not an OS
  security boundary.

The sandbox lifecycle belongs to the canonical Run. Creation, start, snapshot,
pause, resume, failure, and termination are `RunEvent`s. A waiting approval
creates a `SANDBOX_SNAPSHOT` Artifact referenced by the latest Checkpoint, then
releases the worker. Resume/recovery restores that Artifact before scheduling
the next node. Host environment variables are allowlisted, so API keys are not
implicitly copied into guest processes.

---

## 依赖方向

```
cli/ ────────────→ cody/sdk/ → core/*  (via SDK for session mgmt, direct for streaming)
tui/ ────────────→ cody/sdk/ → core/*  (via SDK for session mgmt, direct for streaming)
web/backend/ ────→ core/*  (direct import, Depends() for DI)
cody/sdk/ ───────→ core/*  (direct import, in-process)
                     ↓
              pydantic-ai, sqlite3, httpx, etc.
```

**Rule:** `core/` must NEVER import from `cli/`, `tui/`, `web/`, or `sdk/`. All functionality lives in core; consumers just expose it through their own interface.

**Framework design principle:** Any new consumer can import `core/` and get the full agent experience — tools, sessions, sub-agents, skills, MCP, LSP — without depending on or even knowing about the other consumers.

---

**Last updated:** 2026-03-20
