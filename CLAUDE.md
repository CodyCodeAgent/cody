# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Cody 项目指南

## 项目概述

Cody 是一个**开源 AI Coding Agent 框架**，提供构建 AI 编程 Agent 所需的完整基础设施。

- **Core Engine** (`cody/core/`) — 框架核心，所有功能逻辑，不依赖任何 CLI / Web 框架
- **Python SDK** (`cody/sdk/`) — 框架的主要接入方式，直接包装 core（in-process，无 HTTP）
- **CLI** (`cody/cli/`) — 命令行参考实现（Click）
- **TUI** (`cody/tui/`) — 全屏终端参考实现（Textual）
- **Web Frontend** (`web/src/`) — React + TypeScript SPA 参考实现
- **Web Backend** (`web/backend/`) — FastAPI 应用（端口 8000），提供 HTTP API + Web 功能

`cody/client.py` 为向后兼容 shim，re-export `sdk/` 的公开符号。新代码应直接用 `cody.sdk`。

当前版本：**v2.0.0**（单一来源：`cody/_version.py`）

## 核心定位

> Cody 是 AI Coding Agent 的 **框架**，不是终端工具。
> Core Engine 是产品，CLI/TUI/Web 是基于框架的参考实现。

## 架构要点

```
cody/sdk/ (Python SDK)  →  core/runner.py  →  core/tools/
cli/ / tui/             →  cody/sdk/       →  core/runner.py  →  core/tools/
web/backend/            →  core/runner.py  →  core/tools/
                               ↓
                     pydantic-ai, sqlite3, httpx
```

- `core/` **不允许**导入 `cli/`、`tui/`、`sdk/` 或 `web/`，禁止反向依赖
- CLI/TUI 通过 SDK（`AsyncCodyClient`）访问 core，不直接导入 `AgentRunner`/`SessionStore`
- SDK、CLI、TUI、Web Backend 都是 core 的平行消费者
- 新功能先在 `core/` 实现，再通过 SDK 暴露，最后在参考实现中使用
- 工具注册是声明式的：在 `tools/registry.py` 的 `*_TOOLS` 列表中添加即可
- Web Backend 路由使用 FastAPI `Depends()` 注入依赖；状态管理见 `web/backend/state.py`
- 详细架构图见 `docs/ARCHITECTURE.md`

### 开发流程

新功能的完整路径：`core/` 实现 → SDK 暴露 → Web Backend 路由 → CLI 命令 → 更新文档

### 关键入口文件

- `core/runner.py` — 框架中枢：Agent 创建、工具注册、run/stream 执行、熔断检查、记忆加载
- `core/tools/registry.py` — 声明式工具注册表（`*_TOOLS` 列表），添加新工具只需追加到列表
- `core/deps.py` — CodyDeps 数据类 + ToolContext，工具的依赖注入容器
- `core/prompts.py` — System prompt 构建
- `sdk/client.py` — SDK 客户端：Builder/事件/指标，直接包装 core

## 开发命令

```bash
# 安装（含所有开发依赖）
pip install -e ".[dev]"

# 核心 + SDK 测试（650+ 个）
uv run pytest tests/ -v

# 运行单个测试文件
uv run pytest tests/test_tools.py -v

# 运行匹配名称的测试
uv run pytest tests/ -k "grep" -v

# Web 后端测试（120+ 个）
PYTHONPATH=. uv run pytest web/tests/ -v

# Web 前端测试
cd web && npx vitest run

# Lint（必须零告警）
uv run ruff check cody/ tests/ web/

# 自动修复 lint 问题
uv run ruff check cody/ tests/ web/ --fix

# 类型检查
uv run mypy cody/ --ignore-missing-imports

# 启动 Web（后端 + 前端）
cody-web --dev              # 开发模式
cody-web --port 8000        # 生产模式
```

**CI 矩阵**：Python 3.10–3.13，lint → mypy → core tests → web tests（见 `.github/workflows/python-publish.yml`）

## 代码规范

- **Python 3.10+**，支持 `X | None` 联合类型，不用 `match/case`
- **行宽 100**，ruff 管理
- **类型注解** — 公开函数必须有，内部函数尽量有
- **导入顺序** — stdlib → 三方库 → 项目内部（ruff 自动管理）
- **命名** — 文件 `snake_case.py`，类 `PascalCase`，函数/变量 `snake_case`，常量 `UPPER_SNAKE_CASE`
- **异步测试** 用 `@pytest.mark.asyncio`，`pyproject.toml` 已配 `asyncio_mode = "auto"`
- **文件操作测试** 用 `tmp_path` fixture，不污染真实文件系统
- 工具异常用 `ToolInvalidParams` / `ToolPathDenied` / `ToolPermissionDenied`，不用通用 `ValueError`
- 不依赖真实 API Key — 用 `MockContext` / Pydantic AI `TestModel` 模拟 LLM

### 测试要求

| 变更类型 | 最低测试数 |
|----------|-----------|
| 新工具 | 3 个：正常路径、边界情况、错误处理 |
| 新 API 端点 | 2 个：正常响应、错误响应 |
| 新 CLI 命令 | 1 个：基本调用 |
| Bug 修复 | 必须附带回归测试 |

### Git 规范

- 分支：`main`（稳定）、`feature/xxx`、`fix/xxx`
- 提交信息格式：`<动词> <做了什么>`（英语，祈使句，不加句号）
  - 例：`Add grep tool with regex search and include filter`
  - 例：`Fix path traversal security check using resolve()`

## 文档更新

**开发完新功能后，必须同步更新项目中的所有相关 `.md` 文档**，保持文档与代码同步。

| 目录 | 说明 |
|------|------|
| `./` | 根目录文档（README.md、CHANGELOG.md、CONTRIBUTING.md、CLAUDE.md 等） |
| `docs/` | 所有项目文档（CLI.md、API.md、ARCHITECTURE.md、FEATURES.md、SDK.md 等） |

> **原则**：文档是代码的一部分，不是事后补充。代码合并前，文档必须先更新。

## 版本管理

Python 版本号**单一来源**：`cody/_version.py` → `__version__ = "x.y.z"`

其他位置自动引用，无需手动改：

- `pyproject.toml` → `dynamic = ["version"]`，通过 setuptools 读取 `_version.py`
- `cody/__init__.py` / `cody/sdk/__init__.py` → `from ._version import __version__`
- `cody/core/mcp_client.py` → `from .._version import _version`
- `cody/cli/main.py` → `click.version_option(version=cody.__version__)`

升版本时还需手动更新：`CHANGELOG.md`、`web/package.json`、文档中的版本引用。

## 已知注意事项

1. **循环依赖** — `sub_agent.py` 的 `_execute()` 使用延迟导入，不能移到模块顶部
2. **状态缓存** — `web/backend/state.py` 管理所有单例：Config 按 workdir 缓存（deep copy 返回），SessionStore 全局单例，SkillManager 每次请求新建
3. **可选依赖** — `pip install cody-ai` 仅安装核心 SDK（pydantic-ai, pydantic, httpx），CLI/TUI/Web 需通过 extras 安装（`pip install cody-ai[cli]`、`cody-ai[web]`、`cody-ai[all]`）

## 文档

详细文档在 `docs/` 目录下（架构、API、SDK、CLI、TUI、Skills、配置等）。开发规范见 `CONTRIBUTING.md`。
