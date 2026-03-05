# Cody

**开源 AI Coding Agent 框架** — 构建、定制和部署你自己的 AI 编程 Agent。

[![PyPI](https://img.shields.io/pypi/v/cody-ai.svg)](https://pypi.org/project/cody-ai/)
[![Python](https://img.shields.io/pypi/pyversions/cody-ai.svg)](https://pypi.org/project/cody-ai/)
[![Tests](https://img.shields.io/badge/tests-689%20total-green.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Cody 提供构建 AI 编程 Agent 所需的完整基础设施：**28 个工具、11 个内置技能、MCP/LSP 集成、子 Agent 编排、会话管理和安全体系**。你可以用 SDK 将它嵌入任何 Python 应用，也可以直接用 CLI/TUI/Web 开箱即用。

---

## 为什么选择 Cody？

| 痛点 | Cody 怎么解决 |
|------|--------------|
| 想自建 AI 编码工具，但从零造轮子太重 | 28 个工具 + 安全体系 + Sessions 全现成，专注你的业务逻辑 |
| Claude Code / Cursor 不够灵活，想定制 Agent 行为 | Skills 系统 + 权限控制 + 多模型切换，完全可控 |
| 绑定单一模型厂商，切换成本高 | 多模型支持（Claude、GPT、Gemini、DeepSeek、智谱 GLM、通义千问） |
| 商业产品无法审计、无法私有部署 | 开源 MIT，代码在你手里，可审计、可定制、可离线部署 |

---

## 快速开始

### 方式一：SDK 嵌入（推荐）

```bash
pip install cody-ai    # 仅 4 个核心依赖
```

```python
from cody import AsyncCodyClient

async with AsyncCodyClient(workdir="/path/to/project") as client:
    # 让 AI 执行编码任务
    result = await client.run("创建一个 FastAPI hello world 应用")
    print(result.output)

    # 多轮对话
    session = await client.create_session()
    await client.run("创建 Flask 应用", session_id=session.id)
    await client.run("添加 /health 端点", session_id=session.id)

    # 流式输出
    async for chunk in client.stream("解释这段代码"):
        print(chunk.content, end="")
```

SDK 直接调用核心引擎（in-process），无需启动任何服务。详细文档：[SDK 使用指南](docs/SDK.md)

### 方式二：CLI 开箱即用

```bash
pip install cody-ai[cli]

# 配置模型
cody config setup

# 执行任务
cody run "创建一个 FastAPI hello world 应用"

# 交互对话
cody chat

# 全屏终端
cody tui
```

### 方式三：Web 界面

```bash
pip install cody-ai[web]

cody-web --dev    # 开发模式（含 Vite HMR）
```

---

## 框架能力一览

### 28 个内置工具

| 分类 | 工具 |
|------|------|
| **文件 I/O** | `read_file`, `write_file`, `edit_file`, `list_directory` |
| **搜索** | `grep`, `glob`, `search_files`, `patch` |
| **Shell** | `exec_command` |
| **子代理** | `spawn_agent`, `get_agent_status`, `kill_agent` |
| **MCP** | `mcp_call`, `mcp_list_tools` |
| **Web** | `webfetch`, `websearch` |
| **LSP** | `lsp_diagnostics`, `lsp_definition`, `lsp_references`, `lsp_hover` |
| **文件历史** | `undo_file`, `redo_file`, `list_file_changes` |
| **任务管理** | `todo_write`, `todo_read` |
| **用户交互** | `question` |
| **技能** | `list_skills`, `read_skill` |

### Agent Skills 开放标准

兼容 [Agent Skills](https://agentskills.io/) 开放标准（Claude Code、Cursor、GitHub Copilot 等 26+ 平台采用）。你的 Skills 可以跨平台复用。

```markdown
---
name: git
description: Git 版本控制操作。处理 git 仓库时使用。
metadata:
  author: cody
  version: "1.0"
---
# Git 操作
AI 代理的使用说明...
```

**11 个内置技能：** git, github, docker, npm, python, rust, go, java, web, cicd, testing

**三层优先级：** `.cody/skills/`（项目）> `~/.cody/skills/`（用户）> 内置

### 多模型支持

| 提供商 | 模型示例 |
|--------|----------|
| Anthropic | `anthropic:claude-sonnet-4-0`, `anthropic:claude-opus-4-0` |
| OpenAI | `openai:gpt-4`, `openai:gpt-4-turbo` |
| Google | `google:gemini-pro` |
| DeepSeek | `deepseek:deepseek-coder` |
| 智谱 GLM | `glm-4`（需配置 `model_base_url`） |
| 阿里通义 | `qwen-coder-plus`（需配置 `model_base_url`） |
| 阿里百炼 | `qwen3.5`（需配置 `coding_plan_key`） |
| 任何 OpenAI 兼容 API | 通过 `model_base_url` 配置 |

### 集成能力

- **MCP 集成** — 通过 stdio JSON-RPC 连接外部 MCP 服务器（GitHub、数据库等）
- **LSP 代码智能** — Python (pyright)、TypeScript (tsserver)、Go (gopls)
- **子代理系统** — 孵化专业代理（code/research/test），asyncio 并发执行
- **上下文管理** — 接近 token 限制时自动压缩对话，智能文件分块

### 安全体系

- 工具级权限控制（allow/deny/confirm）
- 路径遍历保护 + 危险命令检测
- 审计日志（SQLite 持久化）
- 速率限制（滑动窗口）
- 文件修改 undo/redo

---

## 四种使用方式

Cody 的核心是 AI 编程引擎（`cody/core/`），以下四种方式共享同一个引擎：

| 方式 | 适用场景 | 安装 |
|------|---------|------|
| **SDK** | 嵌入到你的应用/平台/工具链 | `pip install cody-ai` |
| **CLI** | 终端中快速执行任务 | `pip install cody-ai[cli]` |
| **TUI** | 全屏终端交互（Textual） | `pip install cody-ai[tui]` |
| **Web** | 浏览器界面 + HTTP API | `pip install cody-ai[web]` |

```bash
# 一次性安装全部
pip install cody-ai[all]
```

---

## 配置

```bash
# 交互式配置向导（推荐，首次使用时自动触发）
cody config setup

# 或手动设置环境变量
export CODY_MODEL_API_KEY='sk-ant-...'

# 使用 OpenAI 兼容 API（如智谱 GLM）
export CODY_MODEL='glm-4'
export CODY_MODEL_BASE_URL='https://open.bigmodel.cn/api/paas/v4/'
export CODY_MODEL_API_KEY='sk-...'

# 阿里云百炼 Coding Plan
export CODY_MODEL='qwen3.5'
export CODY_CODING_PLAN_KEY='sk-sp-xxxxx'
```

详细配置：[配置文件详解](docs/CONFIG.md)

---

## 开发

```bash
# 从源码安装
git clone https://github.com/CodyCodeAgent/cody.git
cd cody
pip install -e ".[dev]"

# 运行核心测试（570 个）+ SDK 测试（65 个）
uv run pytest tests/ -v

# Web 后端测试（54 个）
PYTHONPATH=. uv run pytest web/tests/ -v

# Web 前端测试（33 个）
cd web && npx vitest run

# Lint（必须零告警）
uv run ruff check cody/ tests/ web/
```

---

## 文档

### 入门
- [快速入门](docs/QUICKSTART.md) — 15 分钟上手教程
- [CLI 使用指南](docs/CLI.md) — 命令行详细用法
- [TUI 使用指南](docs/TUI.md) — 全屏终端用法

### 框架开发
- [SDK 使用指南](docs/SDK.md) — Python SDK 深度指南
- [技能开发指南](docs/SKILLS.md) — 创建自定义技能
- [架构设计](docs/ARCHITECTURE.md) — 框架架构与数据流
- [API 参考](docs/API.md) — Web API 接口文档

### 参考
- [配置文件详解](docs/CONFIG.md) — 所有配置项说明
- [功能清单](docs/FEATURES.md) — 完整功能列表与路线图
- [开发规范](CONTRIBUTING.md) — 代码规范和贡献指南
- [CHANGELOG](CHANGELOG.md) — 版本历史

---

## 许可证

MIT License

## 致谢

基于以下优秀项目构建：
- [Pydantic AI](https://ai.pydantic.dev/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Textual](https://textual.textualize.io/)
- [Click](https://click.palletsprojects.com/)
- [Rich](https://rich.readthedocs.io/)

---

**最后更新:** 2026-03-05 | **版本:** 1.7.0
