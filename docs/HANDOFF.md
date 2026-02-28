# Cody — Developer Handoff Guide

> 本文档面向接手 Cody 项目的开发者，帮助你快速了解项目全貌、代码结构、开发方法和下一步工作。

---

## 1. 项目概况

Cody 是一个 AI 编程助手，核心理念是 **引擎做厚，壳子做薄**。

- **Core Engine** (`cody/core/`) — 所有功能逻辑所在，不依赖任何 CLI 或 Server 框架
- **CLI** (`cody/cli.py`) — 基于 Click 的命令行壳子，调用 core
- **TUI** (`cody/tui.py`) — 基于 Textual 的全屏交互终端界面，调用 core
- **RPC Server** (`cody/server.py`) — 基于 FastAPI 的 HTTP/WS 服务端，调用 core
- **Python SDK** (`cody/client.py`) — `CodyClient` (同步) + `AsyncCodyClient` (异步) 双客户端
- **Go SDK** (`sdk/go/`) — 零依赖 Go 客户端，覆盖完整 RPC API

新功能 **必须** 先在 core/ 实现，然后在 Server、CLI 和/或 TUI 暴露。

### 技术栈

| 用途 | 库 |
|------|------|
| AI Agent | [pydantic-ai](https://ai.pydantic.dev/) |
| HTTP Server | FastAPI + Uvicorn |
| CLI | Click + Rich |
| TUI | Textual |
| 测试 | pytest + pytest-asyncio |
| Lint | ruff (line-length=100, py39) |
| 配置 | Pydantic BaseModel + JSON |
| 会话 | SQLite (via `SessionStore`) |

### 版本

当前版本：**1.1.0** (`pyproject.toml` / `cody/__init__.py` / `server.py`)

---

## 2. 目录结构

```
cody/
├── cody/
│   ├── __init__.py          # 版本号 + SDK re-export
│   ├── cli.py               # CLI 入口 (Click)
│   ├── tui.py               # TUI 入口 (Textual)
│   ├── client.py            # Python SDK (sync + async)
│   ├── server.py            # RPC Server (FastAPI)
│   └── core/
│       ├── __init__.py      # 公开 API (__all__)
│       ├── config.py        # 配置模型 (Pydantic)
│       ├── runner.py        # AgentRunner + CodyDeps
│       ├── tools.py         # 所有内置工具函数
│       ├── session.py       # SQLite 会话持久化
│       ├── skill_manager.py # Skill 三层加载
│       ├── sub_agent.py     # 子 Agent 编排
│       ├── mcp_client.py    # MCP 协议客户端
│       ├── lsp_client.py    # LSP 语言服务客户端
│       ├── context.py       # 上下文管理 (compact, chunk)
│       ├── errors.py        # 结构化错误 (ErrorCode, CodyAPIError)
│       ├── web.py           # Web 搜索 + 抓取
│       ├── audit.py         # 审计日志 (SQLite)
│       ├── auth.py          # OAuth 认证 (HMAC-SHA256 token)
│       ├── permissions.py   # 工具级权限 (allow/deny/confirm)
│       ├── file_history.py  # 文件 undo/redo 快照
│       └── rate_limiter.py  # 滑动窗口限流
├── tests/                   # 474 个测试
├── docs/
│   ├── API.md               # RPC API 文档
│   ├── ARCHITECTURE.md      # 架构设计文档
│   ├── FEATURES.md          # 功能清单 + 路线图
│   └── HANDOFF.md           # 本文档
├── skills/                  # 内置 Skills (11 个)
├── templates/               # CI/CD 模板 (GitHub Actions)
├── CONTRIBUTING.md          # 开发规范
├── pyproject.toml           # 构建配置
└── README.md                # 项目简介
```

---

## 3. 核心模块说明

### 3.1 AgentRunner (`core/runner.py`)

项目的 **中枢**。负责：
- 创建 Pydantic AI `Agent` 实例
- 通过 `_resolve_model()` 解析模型：支持内置 provider 字符串和自定义 OpenAI 兼容 API
- 注册所有工具 (tools, skills, MCP, LSP, sub-agent, web)
- 组装 `CodyDeps` 依赖注入给工具函数
- 提供 `run()` / `run_stream()` / `run_sync()` 三种执行方式
- 提供 `run_with_session()` / `run_stream_with_session()` 会话感知版本

**依赖图：**
```
AgentRunner
  ├── Config
  ├── SkillManager
  ├── MCPClient (可选, 有 MCP 配置时才创建)
  ├── SubAgentManager
  ├── LSPClient
  ├── AuditLogger
  ├── PermissionManager
  ├── FileHistory
  └── tools.* (通过 agent.tool() 注册)
```

### 3.2 工具系统 (`core/tools.py`)

所有工具函数签名统一为 `async def tool_name(ctx: RunContext[CodyDeps], ...) -> str`。

**工具列表：**

| 类别 | 工具 |
|------|------|
| 文件 | `read_file`, `write_file`, `edit_file`, `list_directory`, `search_files` |
| 搜索 | `grep`, `glob`, `patch` |
| 命令 | `exec_command` |
| Skill | `list_skills`, `read_skill` |
| 子 Agent | `spawn_agent`, `get_agent_status`, `kill_agent` |
| MCP | `mcp_call`, `mcp_list_tools` |
| Web | `webfetch`, `websearch` |
| LSP | `lsp_diagnostics`, `lsp_definition`, `lsp_references`, `lsp_hover` |
| 文件历史 | `undo_file`, `redo_file`, `list_file_changes` |
| 任务管理 | `todo_write`, `todo_read` |
| 用户交互 | `question` |

**安全机制：** 所有可变工具先调用 `_check_permission(ctx, tool_name)` 检查权限；文件/命令工具再调用 `_resolve_and_check(workdir, path)` 做路径遍历防护，确保操作不会逃出 workdir。

### 3.3 会话系统 (`core/session.py`)

基于 SQLite，`SessionStore` 管理会话的 CRUD：
- `create_session()` → 创建会话
- `get_session(id)` → 获取会话 + 消息
- `list_sessions(limit)` → 最近会话列表
- `delete_session(id)` → 删除会话
- `add_message(session_id, role, content)` → 添加消息

数据库文件默认在 `~/.cody/sessions.db`。

### 3.4 Skill 系统 (`core/skill_manager.py`) — Agent Skills 开放标准

完全兼容 [Agent Skills 开放标准](https://agentskills.io/)（Anthropic 发布，26+ 平台采纳）。

**SKILL.md 格式：** YAML frontmatter（`name`、`description`、可选 `license`/`compatibility`/`metadata`/`allowed-tools`）+ Markdown body。

三层优先级加载：
1. `.cody/skills/` — 项目级 (最高优先级)
2. `~/.cody/skills/` — 用户级
3. `{install_dir}/skills/` — 内置

**渐进式加载：** 启动时只解析 frontmatter（name + description），`skill.instructions` 按需加载完整 body。`to_prompt_xml()` 生成 `<available_skills>` XML 注入 system prompt，实现模型驱动的 Skill 发现。

**校验：** `validate_skill(path)` 检查 frontmatter 必填字段、name 格式、目录名一致性。

**内置 Skills（11 个）：** git, github, docker, npm, python, rust, go, java, web, cicd, testing

启用/禁用通过 `config.skills.enabled` / `config.skills.disabled` 控制。

### 3.5 子 Agent 系统 (`core/sub_agent.py`)

`SubAgentManager` 用 asyncio 编排并发子 Agent：
- 4 种类型：`code`, `research`, `test`, `generic`
- 每种类型有不同的工具集和 system prompt
- 最大并发 5 个，默认超时 300s
- 使用 `asyncio.Semaphore` 控制并发

**注意：** `sub_agent.py` 的 `_execute()` 方法中有延迟导入 (`from . import tools`, `from .runner import CodyDeps`)，这是为了打破 `runner → sub_agent → runner` 的循环依赖，**不要移到模块级别**。

### 3.6 MCP 客户端 (`core/mcp_client.py`)

实现 stdio JSON-RPC 协议，管理 MCP Server 子进程：
- `start_all()` / `stop_all()` — 批量管理 Server 生命周期
- `call_tool(server, tool, params)` — 调用 MCP Server 的工具
- `list_tools(server)` — 发现 MCP Server 提供的工具

### 3.7 LSP 客户端 (`core/lsp_client.py`)

管理语言服务器进程 (pyright / typescript-language-server / gopls)：
- Content-Length 帧 JSON-RPC 通信
- 提供诊断、跳转定义、查找引用、悬停等能力

### 3.8 上下文管理 (`core/context.py`)

- `compact_messages()` — 接近 token 窗口限制时自动摘要压缩旧消息
- `chunk_file()` — 大文件带重叠分块切割
- `select_relevant_context()` — 关键词匹配 + token 预算控制

Auto-compact 已接入 `AgentRunner.run()` 和 `run_stream()`，通过 `_compact_history_if_needed()` 方法自动触发。

### 3.9 结构化错误 (`core/errors.py`)

统一错误码体系：
```python
class ErrorCode(str, Enum):
    INVALID_PARAMS = "INVALID_PARAMS"      # 400
    PERMISSION_DENIED = "PERMISSION_DENIED" # 403
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"       # 404
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND" # 404
    SKILL_NOT_FOUND = "SKILL_NOT_FOUND"     # 404
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"     # 404
    AGENT_LIMIT_REACHED = "AGENT_LIMIT_REACHED" # 429
    TOOL_ERROR = "TOOL_ERROR"               # 500
    AGENT_ERROR = "AGENT_ERROR"             # 500
    SERVER_ERROR = "SERVER_ERROR"           # 500
```

Server 和 SDK 都使用 `CodyAPIError` 异常，序列化为 `{"error": {"code": "...", "message": "..."}}`。

---

## 4. Server API 概览

详细文档见 `docs/API.md`。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/run` | POST | 执行 Agent 任务 |
| `/run/stream` | POST | SSE 流式执行 |
| `/tool` | POST | 直接调用工具 |
| `/skills` | GET | 列出所有 Skill |
| `/skills/{name}` | GET | Skill 详情 + 文档 |
| `/sessions` | POST/GET | 创建/列出会话 |
| `/sessions/{id}` | GET/DELETE | 会话详情/删除 |
| `/agent/spawn` | POST | 孵化子 Agent |
| `/agent/{id}` | GET/DELETE | 查询/终止子 Agent |
| `/audit` | GET | 审计日志查询 |
| `/ws` | WebSocket | 实时双向交互 |

---

## 5. Python SDK 用法

```python
from cody import AsyncCodyClient

async with AsyncCodyClient("http://localhost:8000") as client:
    # 一次性调用
    result = await client.run("创建 hello.py")
    print(result.output)

    # 多轮会话
    session = await client.create_session()
    r1 = await client.run("创建 Flask 项目", session_id=session.id)
    r2 = await client.run("添加 /health 端点", session_id=session.id)

    # 流式响应
    async for chunk in client.stream("解释这段代码"):
        print(chunk.content, end="")

    # 直接调用工具
    result = await client.tool("read_file", {"path": "main.py"})
```

同步版：
```python
from cody import CodyClient

client = CodyClient("http://localhost:8000")
result = client.run("创建 hello.py")
skills = client.list_skills()
```

SDK 内置自动重试 (`max_retries=3`, 指数退避 0.5s→8s) 和结构化错误解析。

---

## 6. 开发流程

### 环境搭建

```bash
git clone <repo>
cd cody
pip install -e ".[dev]"
```

### 运行测试

```bash
# 全量测试
python3 -m pytest tests/ -v

# 单文件
python3 -m pytest tests/test_tools.py -v

# 按名称过滤
python3 -m pytest tests/ -k "grep" -v
```

### Lint

```bash
python3 -m ruff check cody/ tests/
python3 -m ruff check cody/ tests/ --fix  # 自动修复
```

### 运行 TUI

```bash
cody tui                       # 启动全屏交互界面
cody tui --continue            # 继续上次会话
cody tui --session <id>        # 恢复指定会话
cody-tui                       # 直接启动（console_scripts）
```

### 运行 Server

```bash
cody-server                    # 默认 0.0.0.0:8000
cody-server --port 9000       # 指定端口
```

### 测试文件对应关系

| 测试文件 | 被测模块 |
|----------|----------|
| `test_tools.py` | `core/tools.py` |
| `test_session.py` | `core/session.py` |
| `test_runner.py` | `core/runner.py` |
| `test_server.py` | `server.py` |
| `test_cli.py` | `cli.py` |
| `test_client.py` | `client.py` |
| `test_config.py` | `core/config.py` |
| `test_skill_manager.py` | `core/skill_manager.py` |
| `test_sub_agent.py` | `core/sub_agent.py` |
| `test_mcp.py` | `core/mcp_client.py` |
| `test_lsp.py` | `core/lsp_client.py` |
| `test_web.py` | `core/web.py` |
| `test_context.py` | `core/context.py` |
| `test_errors.py` | `core/errors.py` |
| `test_retry.py` | SDK retry 逻辑 |
| `test_websocket.py` | WebSocket 端点 |
| `test_audit.py` | `core/audit.py` |
| `test_auth.py` | `core/auth.py` |
| `test_permissions.py` | `core/permissions.py` |
| `test_file_history.py` | `core/file_history.py` |
| `test_rate_limiter.py` | `core/rate_limiter.py` |
| `test_tui.py` | `tui.py` |

---

## 7. 已知问题和注意事项

### 架构注意

1. **循环依赖** — `sub_agent.py` 中的 `_execute()` 使用延迟导入，不能移到模块顶部
2. **Server 单例** — `server.py` 中 `_sub_agent_manager` 用 `asyncio.Lock()` 延迟初始化，不是最优方案但能工作。生产环境建议改为依赖注入
3. **SessionStore** — 每次请求 new 一个 `SessionStore()` 实例，每个实例独立连接 SQLite。并发场景 SQLite 可能成瓶颈

### 文档状态

| 文档 | 状态 | 说明 |
|------|------|------|
| `docs/API.md` | 准确 | 与代码同步 |
| `docs/FEATURES.md` | 准确 | 含完整路线图 |
| `docs/ARCHITECTURE.md` | 准确 | 完整架构图、组件说明、数据流 |
| `CONTRIBUTING.md` | 准确 | 包含完整模块测试状态表 |
| `README.md` | 准确 | 全功能概览 |

### 测试注意

- 所有测试 **不需要** 真实 API Key，使用 `MockContext` 或 pydantic-ai `TestModel`
- 异步测试使用 `@pytest.mark.asyncio`，`pyproject.toml` 已配置 `asyncio_mode = "auto"`
- 文件操作测试使用 `tmp_path` fixture，不污染文件系统

---

## 8. 版本历史

详见 [CHANGELOG.md](../CHANGELOG.md)。

---

## 9. 快速上手路径

如果你刚接手项目，建议按这个顺序熟悉：

1. **跑通测试** — `pip install -e ".[dev]" && python3 -m pytest tests/ -v`
2. **看 `core/runner.py`** — 理解引擎中枢
3. **看 `core/tools.py`** — 理解工具注册模式
4. **看 `server.py`** — 理解 Server 如何调用 core
5. **看 `CONTRIBUTING.md`** — 了解代码规范
6. **看 `docs/API.md`** — 了解对外 API

有问题看测试——每个模块都有对应的测试文件，是最好的 "活文档"。

---

**最后更新：** 2026-02-28
