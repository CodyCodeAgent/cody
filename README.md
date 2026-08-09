# Cody

**开源 Agent Runtime + Coding Agent 参考实现** — 构建可嵌入、可编排、可恢复、可治理的 AI Agent。

[![PyPI](https://img.shields.io/pypi/v/cody-ai.svg)](https://pypi.org/project/cody-ai/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://pypi.org/project/cody-ai/)
[![Tests](https://img.shields.io/badge/tests-passing-green.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Cody 提供构建 AI 编程 Agent 所需的完整基础设施：**Canonical Agent Runtime、30 个工具（28 core + 2 MCP）、可恢复工作流、Agent Skills、MCP/LSP、多 Agent 编排、Quality Gate、Sandbox 和完整治理/观测能力**。你可以用 SDK 将它嵌入任何 Python 应用，也可以直接用 CLI/TUI/Web 开箱即用。

---

## 为什么选择 Cody？

| 痛点 | Cody 怎么解决 |
|------|--------------|
| 想自建 AI 编码工具，但从零造轮子太重 | Runtime + 30 个工具 + Sessions + Sandbox 全现成，专注你的业务逻辑 |
| Claude Code / Cursor 不够灵活，想定制 Agent 行为 | Skills 系统 + 权限控制 + 多模型切换，完全可控 |
| 绑定单一模型厂商，切换成本高 | 使用标准 OpenAI-compatible 接口，可连接 DeepSeek、通义、GLM、本地模型和兼容网关 |
| 商业产品无法审计、无法私有部署 | 开源 MIT，代码在你手里，可审计、可定制、可离线部署 |

---

## 快速开始

### 方式一：SDK 嵌入（推荐）

```bash
pip install cody-ai    # 3 个直接核心依赖
```

```python
from cody import AsyncCodyClient

async with AsyncCodyClient(workdir="/path/to/project") as client:
    # 让 AI 执行编码任务
    result = await client.run("创建一个 FastAPI hello world 应用")
    print(result.output)

    # 多轮对话（自动创建 session）
    r1 = await client.run("创建 Flask 应用")
    await client.run("添加 /health 端点", session_id=r1.session_id)

    # 流式输出
    async for chunk in client.run_stream("解释这段代码"):
        print(chunk.content, end="")
```

SDK 直接调用核心引擎（in-process），无需启动任何服务。详细文档：[SDK 使用指南](docs/SDK.md)

### 方式二：CLI 开箱即用

```bash
pip install cody-ai[cli]

# `cody tui` 同时需要 CLI 与 Textual（也可以安装 cody-ai[all]）
pip install 'cody-ai[cli,tui]'

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

cody-web run --dev    # 开发模式（含 Vite HMR）
```

---

## 框架能力一览

### 30 个内置工具

| 分类 | 工具 |
|------|------|
| **文件 I/O** | `read_file`, `write_file`, `edit_file`, `list_directory` |
| **搜索** | `grep`, `glob`, `search_files`, `patch` |
| **Shell** | `exec_command` |
| **子代理** | `spawn_agent`, `get_agent_status`, `kill_agent`, `resume_agent` |
| **MCP** | `mcp_call`, `mcp_list_tools` |
| **Web** | `webfetch`, `websearch` |
| **LSP** | `lsp_diagnostics`, `lsp_definition`, `lsp_references`, `lsp_hover` |
| **文件历史** | `undo_file`, `redo_file`, `list_file_changes` |
| **任务管理** | `todo_write`, `todo_read` |
| **用户交互** | `question` |
| **记忆** | `save_memory` |
| **技能** | `list_skills`, `read_skill` |

### Agent Skills 开放标准

兼容 [Agent Skills](https://agentskills.io/) 开放标准，使用可移植的 YAML frontmatter +
Markdown 目录格式，便于与其他兼容 Agent 工具复用。

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

**自定义技能：** 在 `.cody/skills/` 或 `~/.cody/skills/` 下创建 SKILL.md，AI 自动发现并按需加载。

**加载优先级：** `custom_dirs` > `.cody/skills/`（项目）>
`~/.cody/skills/`（用户）> 内置 Skills

### 模型接入

Cody 的模型层使用 OpenAI-compatible Chat Completions 接口。配置模型名称、Base URL
和 API Key 即可切换提供商；模型名必须以目标端点实际支持的名称为准。

| 提供商/部署 | 模型示例 | Base URL 示例 |
|-------------|----------|---------------|
| DeepSeek | `deepseek-chat`、`deepseek-reasoner` | `https://api.deepseek.com/v1` |
| 阿里云百炼 | `qwen-plus` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 智谱 GLM | `glm-4` | `https://open.bigmodel.cn/api/paas/v4/` |
| 本地或企业网关 | 由网关决定 | 任意 OpenAI-compatible `/v1` 地址 |

### 集成能力

- **MCP 集成** — 通过 stdio JSON-RPC 连接外部 MCP 服务器（GitHub、数据库等）
- **LSP 代码智能** — Python (pyright)、TypeScript (tsserver)、Go (gopls)
- **子代理系统** — 孵化专业代理（code/research/test），asyncio 并发执行
- **上下文管理** — 接近 token 限制时自动压缩对话，智能文件分块
- **熔断器** — Token/成本上限 + 死循环检测，自动终止失控 Agent
- **跨任务记忆** — AI 自动积累项目经验，注入后续会话
- **人工交互** — AI 主动提问 + 用户随时输入，双向互动
- **Canonical Runtime** — Run/Step/Event/Checkpoint/Artifact/Approval 共享一条持久化主链
- **工作流与多 Agent** — sequential/parallel/join/fallback、团队任务 DAG、确定性结果合并
- **Quality Gate** — 测试、lint、风险检查和有限次数自动修复循环

### 安全体系

- 工具级权限控制（allow/deny/confirm）
- 路径遍历保护 + 危险命令检测
- 审计日志（SQLite 持久化）
- 速率限制（滑动窗口）
- 文件修改 undo/redo
- macOS Seatbelt、Linux Bubblewrap、Docker/Podman，以及可注入 transport 的 Remote Sandbox adapter
- 审批等待持久化、进程重启恢复、工具幂等收据和秘密脱敏

---

## 四种使用方式

Cody 的核心是 AI 编程引擎（`cody/core/`），以下四种方式共享同一个引擎：

| 方式 | 适用场景 | 安装 |
|------|---------|------|
| **SDK** | 嵌入到你的应用/平台/工具链 | `pip install cody-ai` |
| **CLI** | 终端中快速执行任务 | `pip install cody-ai[cli]` |
| **TUI** | 全屏终端交互（Textual） | `pip install 'cody-ai[cli,tui]'` |
| **Web** | 浏览器界面 + HTTP API | `pip install cody-ai[web]` |

```bash
# 安装全部本地产品表面（SDK + CLI + TUI + Web）
pip install cody-ai[all]

# PostgreSQL / S3 生产后端
pip install cody-ai[production]
```

---

## 配置

```bash
# 交互式配置向导（保存模型和 Base URL，不持久化密钥）
cody config setup

# 密钥只通过环境变量或部署平台的 secret manager 注入
export CODY_MODEL_API_KEY='your-api-key'

# 使用 OpenAI 兼容 API（如智谱 GLM）
export CODY_MODEL='glm-4'
export CODY_MODEL_BASE_URL='https://open.bigmodel.cn/api/paas/v4/'
export CODY_MODEL_API_KEY='your-api-key'

# 阿里云百炼 Coding Plan
export CODY_MODEL='qwen-plus'
export CODY_MODEL_API_KEY='your-api-key'
```

详细配置：[配置文件详解](docs/CONFIG.md)

---

## 开发

```bash
# 从源码安装
git clone https://github.com/CodyCodeAgent/cody.git
cd cody
pip install -e ".[dev]"

# 运行全部 Python 测试（包含 core、SDK 与 Web backend）
uv run pytest -q

# Web 后端专项测试
uv run pytest web/tests/ -q

# Web 前端测试与生产构建
cd web && npm test -- --run && npm run build

# Lint（必须零告警）
uv run ruff check .
```

---

## 文档

完整、可搜索的 GitHub Pages 文档：[https://codycodeagent.github.io/cody/](https://codycodeagent.github.io/cody/)

站点将内容分为两类：**教程**按真实任务带你完成闭环，**指南**按能力域提供完整参考。

### 入门
- [快速入门](docs/QUICKSTART.md) — 15 分钟上手教程
- [CLI 使用指南](docs/CLI.md) — 命令行详细用法
- [TUI 使用指南](docs/TUI.md) — 全屏终端用法

### 框架开发
- [Runtime 使用与部署](docs/RUNTIME.md) — Run、Workflow、恢复、存储、治理与扩展
- [Sandbox 指南](docs/SANDBOX.md) — 隔离后端、网络策略、生命周期与部署要求
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

**最后更新:** 2026-08-09 | **版本:** 3.0.1
