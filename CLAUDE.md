# CLAUDE.md — Cody 项目指南

## 项目概述

Cody 是一个 AI 编程助手，核心理念是 **引擎做厚，壳子做薄**。

- **Core Engine** (`cody/core/`) — 所有功能逻辑，不依赖任何 CLI / Server 框架
- **CLI** (`cody/cli.py`) — Click 命令行
- **TUI** (`cody/tui.py`) — Textual 全屏终端
- **Web Frontend** (`web/src/`) — React + TypeScript SPA（项目管理 + 实时对话）
- **Web Backend** (`web/backend/`) — 统一 FastAPI 应用（端口 8000），提供 Web + RPC 端点，直接导入 core
- **Python SDK** (`cody/client.py`) — CodyClient (同步) + AsyncCodyClient (异步)，in-process 封装 core

当前版本：**v1.3.0**

## 架构要点

```
cli.py / tui.py  →  core/runner.py  →  core/tools.py
                        ↓
                pydantic-ai, sqlite3, httpx

web/src/ (React) → web/backend/ (FastAPI:8000) → core/
cody/client.py (Python SDK) → core/（in-process，无 HTTP）
```

- `core/` **不允许**导入 `cli.py`、`tui.py` 或 `web/`
- 新功能先在 `core/` 实现，再在 shell 层暴露
- 工具注册是声明式的：在 `tools.py` 底部的 `*_TOOLS` 列表中添加即可，不需要改 `runner.py`
- 详细架构图见 `docs/ARCHITECTURE.md`

## 关键文件

| 文件 | 作用 |
|------|------|
| `core/runner.py` | 中枢引擎 — Agent 创建、工具注册、run/stream 执行 |
| `core/tools.py` | 28 个工具函数 + 底部声明式工具注册表 |
| `core/errors.py` | 错误码 + ToolError 异常层级（Web Backend 按类型映射 HTTP 状态码） |
| `core/config.py` | Pydantic 配置模型，支持全局/项目级 JSON |
| `core/deps.py` | CodyDeps 数据类，工具的依赖注入容器 |
| `core/project_instructions.py` | CODY.md 加载逻辑 — 全局 + 项目级合并，注入系统提示 |
| `core/sub_agent.py` | 子 Agent 编排，`_execute()` 有延迟导入（打破循环依赖） |
| `core/skill_manager.py` | Agent Skills 开放标准，三层优先级加载 |
| `client.py` | Python SDK — core 的 in-process 封装（CodyClient + AsyncCodyClient） |
| `web/backend/app.py` | 统一 FastAPI 应用 — Web + RPC 路由、中间件、静态文件 |
| `web/backend/state.py` | 单例状态管理 — Config 缓存、SessionStore、AuditLogger 等 |
| `web/backend/routes/` | 所有 HTTP/WS 路由 — run、tool、sessions、skills、agents、ws、projects、chat |

## CLI 命令速查

```bash
# 单次执行
cody run "create hello.py"
cody run --thinking "complex analysis"     # 启用思考模式
cody run -v "debug this"                   # 显示工具调用结果
cody run --workdir /path/to/project "fix"  # 指定工作目录

# 交互对话
cody chat                                  # 多轮 REPL
cody chat --continue                       # 续上次会话
cody chat --session <id>                   # 恢复指定会话
cody chat --workdir /path/to/project       # 指定工作目录

# TUI
cody tui                                   # 全屏终端
cody tui --continue                        # 续上次会话
cody tui --workdir /path/to/project        # 指定工作目录

# 会话管理
cody sessions list                         # 列出会话
cody sessions show <id>                    # 查看会话内容
cody sessions delete <id>                  # 删除会话

# Skills 管理
cody skills list                           # 列出所有技能
cody skills show git                       # 查看技能文档
cody skills enable github                  # 启用技能
cody skills disable docker                 # 禁用技能

# 配置
cody config show                           # 查看当前配置
cody config set model "anthropic:claude-sonnet-4-0"  # 设置模型
cody init                                  # 初始化 .cody/ 目录
```

所有命令默认在当前目录工作，`--workdir` 可覆盖。

## 开发命令

```bash
# 安装
pip install -e ".[dev]"

# 核心测试（481 个，不需要真实 API Key）
python3 -m pytest tests/ -v

# Web 后端测试（45 个）
PYTHONPATH=. python3 -m pytest web/tests/ -v

# Web 前端测试（33 个）
cd web && npx vitest run

# Lint（必须零告警）
python3 -m ruff check cody/ tests/ web/

# 启动 Web（后端 + 前端）
cody-web --dev              # 开发模式（含 Vite HMR）
cody-web --port 8000        # 生产模式（托管 dist/）

# 启动 TUI
cody tui
```

## 文档更新

**开发完新功能后，必须同步更新项目中的所有相关 `.md` 文档**，保持文档与代码同步。

### 需要检查的文档目录

| 目录 | 说明 |
|------|------|
| `./` | 根目录文档（README.md、CHANGELOG.md、CONTRIBUTING.md、CLAUDE.md 等） |
| `docs/` | 所有项目文档（CLI.md、API.md、ARCHITECTURE.md、FEATURES.md 等） |

### 检查清单

提交前确认所有相关的 `.md` 文档已更新：

- [ ] 根目录文档 — README.md、CHANGELOG.md、CONTRIBUTING.md、CLAUDE.md 等
- [ ] docs/ 目录文档 — CLI.md、API.md、ARCHITECTURE.md、FEATURES.md 等

> **原则**：文档是代码的一部分，不是事后补充。代码合并前，文档必须先更新。
> 
> **提示**：使用 `find . -name "*.md"` 列出所有 Markdown 文档，逐一检查是否需要更新。

---

## 版本管理

版本号在 **3 个位置**，必须同步更新：

1. `pyproject.toml` → `version = "x.y.z"`
2. `cody/__init__.py` → `__version__ = "x.y.z"`（`web/backend/` 自动引用此值）
3. `cody/core/mcp_client.py` → `clientInfo.version`

同时更新 `CHANGELOG.md` 添加版本条目，`CONTRIBUTING.md` 中的版本号。

## 代码规范

- **Python 3.9+**，不用 `match/case`
- **行宽 100**，ruff 管理
- **异步测试** 用 `@pytest.mark.asyncio`，`pyproject.toml` 已配 `asyncio_mode = "auto"`
- **文件操作测试** 用 `tmp_path` fixture
- 工具异常用 `ToolInvalidParams` / `ToolPathDenied` / `ToolPermissionDenied`，不用通用 `ValueError`

## 已知注意事项

1. **循环依赖** — `sub_agent.py` 的 `_execute()` 使用延迟导入，不能移到模块顶部
2. **状态缓存** — `web/backend/state.py` 管理所有单例：Config 按 workdir 缓存（deep copy 返回），SessionStore 全局单例，SkillManager 每次请求新建（保证读最新 skill 文件）

## 文档结构

| 文档 | 内容 |
|------|------|
| `docs/ARCHITECTURE.md` | 架构图、组件说明、数据流 |
| `docs/API.md` | RPC API 接口文档 |
| `docs/FEATURES.md` | 功能清单 + 路线图 |
| `CONTRIBUTING.md` | 开发规范 + 快速上手路径 |
| `CHANGELOG.md` | 版本历史 |
