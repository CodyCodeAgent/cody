# CLAUDE.md — Cody 项目指南

## 项目概述

Cody 是一个**开源 AI Coding Agent 框架**，提供构建 AI 编程 Agent 所需的完整基础设施。

- **Core Engine** (`cody/core/`) — 框架核心，所有功能逻辑，不依赖任何 CLI / Web 框架
- **Python SDK** (`cody/sdk/`) — 框架的主要接入方式，直接包装 core（in-process，无 HTTP）
- **CLI** (`cody/cli/`) — 命令行参考实现（Click）
- **TUI** (`cody/tui/`) — 全屏终端参考实现（Textual）
- **Web Frontend** (`web/src/`) — React + TypeScript SPA 参考实现
- **Web Backend** (`web/backend/`) — FastAPI 应用（端口 8000），提供 HTTP API + Web 功能

`cody/client.py` 为向后兼容 shim，re-export `sdk/` 的公开符号。

当前版本：**v1.7.0**

## 核心定位

> Cody 是 AI Coding Agent 的 **框架**，不是终端工具。
> Core Engine 是产品，CLI/TUI/Web 是基于框架的参考实现。

**目标用户优先级：**
1. **想自建 AI 编码工具的团队** — 用 Cody 框架快速搭建
2. **想定制 Agent 行为的开发者** — Skills + 多模型 + 权限控制
3. **个人程序员** — CLI/TUI/Web 开箱即用

## 架构要点

```
cody/sdk/ (Python SDK)  →  core/runner.py  →  core/tools.py
cli/ / tui/             →  core/runner.py  →  core/tools.py
web/backend/            →  core/runner.py  →  core/tools.py
                               ↓
                     pydantic-ai, sqlite3, httpx
```

- `core/` **不允许**导入 `cli/`、`tui/` 或 `web/`
- SDK、CLI、TUI、Web Backend 都是 core 的平行消费者
- 新功能先在 `core/` 实现，再通过 SDK 暴露，最后在参考实现中使用
- 工具注册是声明式的：在 `tools.py` 底部的 `*_TOOLS` 列表中添加即可
- 详细架构图见 `docs/ARCHITECTURE.md`

## 关键文件

| 文件 | 作用 |
|------|------|
| `core/prompt.py` | 多模态 Prompt 类型 — ImageData, MultimodalPrompt, Prompt |
| `core/runner.py` | 框架中枢 — Agent 创建、工具注册、run/stream 执行 |
| `core/tools.py` | 28 个工具函数 + 底部声明式工具注册表 |
| `core/errors.py` | 错误码 + ToolError 异常层级（Web Backend 按类型映射 HTTP 状态码） |
| `core/config.py` | Pydantic 配置模型，支持全局/项目级 JSON，is_ready() 检查 |
| `core/setup.py` | 交互式配置向导数据层 — SetupAnswers + build_config_from_answers |
| `core/deps.py` | CodyDeps 数据类 + ToolContext，工具的依赖注入容器 |
| `shared.py` | CLI/TUI 共享工具函数 — spinner、格式化、config 路径解析 |
| `core/project_instructions.py` | CODY.md 加载逻辑 — 全局 + 项目级合并，注入系统提示 |
| `core/sub_agent.py` | 子 Agent 编排，`_execute()` 有延迟导入（打破循环依赖） |
| `core/skill_manager.py` | Agent Skills 开放标准，三层优先级加载 |
| `sdk/client.py` | SDK 客户端 — Builder/事件/指标，直接包装 core |
| `sdk/types.py` | SDK 响应类型 — RunResult, Usage, StreamChunk 等 |
| `sdk/errors.py` | SDK 错误层级 — 10 种细粒度错误类型 |
| `sdk/config.py` | SDK 配置 — SDKConfig, ModelConfig, config() 工厂 |
| `client.py` | 向后兼容 shim — re-export `sdk/` 的公开符号 |
| `web/backend/app.py` | FastAPI 应用 — Web + API 路由、中间件、静态文件 |
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

# TUI
cody tui                                   # 全屏终端

# 会话管理
cody sessions list / show <id> / delete <id>

# Skills 管理
cody skills list / show <name> / enable <name> / disable <name>

# 配置
cody config setup / show / set <key> <value>
cody init                                  # 初始化 .cody/ 目录
```

## 开发命令

```bash
# 安装
pip install -e ".[dev]"

# 核心测试（570 个）+ SDK 测试（65 个）
uv run pytest tests/ -v

# Web 后端测试（54 个）
PYTHONPATH=. uv run pytest web/tests/ -v

# Web 前端测试（33 个）
cd web && npx vitest run

# Lint（必须零告警）
uv run ruff check cody/ tests/ web/

# 启动 Web（后端 + 前端）
cody-web --dev              # 开发模式
cody-web --port 8000        # 生产模式
```

## 文档更新

**开发完新功能后，必须同步更新项目中的所有相关 `.md` 文档**，保持文档与代码同步。

### 需要检查的文档

| 目录 | 说明 |
|------|------|
| `./` | 根目录文档（README.md、CHANGELOG.md、CONTRIBUTING.md、CLAUDE.md 等） |
| `docs/` | 所有项目文档（CLI.md、API.md、ARCHITECTURE.md、FEATURES.md、SDK.md 等） |

> **原则**：文档是代码的一部分，不是事后补充。代码合并前，文档必须先更新。

---

## 版本管理

Python 版本号**单一来源**：`cody/_version.py` → `__version__ = "x.y.z"`

其他位置自动引用，无需手动改：

- `pyproject.toml` → `dynamic = ["version"]`，通过 setuptools 读取 `_version.py`
- `cody/__init__.py` / `cody/sdk/__init__.py` → `from ._version import __version__`
- `cody/core/mcp_client.py` → `from .._version import _version`
- `cody/cli/main.py` → `click.version_option(version=cody.__version__)`

升版本时还需手动更新：`CHANGELOG.md`、`web/package.json`、文档中的版本引用。

## 代码规范

- **Python 3.9+**，不用 `match/case`
- **行宽 100**，ruff 管理
- **异步测试** 用 `@pytest.mark.asyncio`，`pyproject.toml` 已配 `asyncio_mode = "auto"`
- **文件操作测试** 用 `tmp_path` fixture
- 工具异常用 `ToolInvalidParams` / `ToolPathDenied` / `ToolPermissionDenied`，不用通用 `ValueError`

## 已知注意事项

1. **循环依赖** — `sub_agent.py` 的 `_execute()` 使用延迟导入，不能移到模块顶部
2. **状态缓存** — `web/backend/state.py` 管理所有单例：Config 按 workdir 缓存（deep copy 返回），SessionStore 全局单例，SkillManager 每次请求新建
3. **可选依赖** — `pip install cody-ai` 仅安装核心 SDK（4 个依赖），CLI/TUI/Web 需通过 extras 安装

## 文档结构

| 文档 | 内容 |
|------|------|
| `docs/ARCHITECTURE.md` | 框架架构、组件说明、数据流 |
| `docs/API.md` | Web API 接口文档 |
| `docs/FEATURES.md` | 功能清单 + 路线图 |
| `docs/SDK.md` | Python SDK 使用文档 |
| `docs/CLI.md` | CLI 使用指南 |
| `docs/TUI.md` | TUI 使用指南 |
| `docs/SKILLS.md` | 技能开发指南 |
| `docs/CONFIG.md` | 配置文件详解 |
| `docs/QUICKSTART.md` | 快速入门教程 |
| `CONTRIBUTING.md` | 开发规范 + 快速上手 |
| `CHANGELOG.md` | 版本历史 |
