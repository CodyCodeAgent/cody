# Cody

**AI 编码引擎** — 支持 RPC Server、动态技能、MCP 集成和 LSP 代码智能。

[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-497%20total-green.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**核心理念：引擎做厚，壳子做薄。** CLI、TUI 和 Server 都是基于核心引擎的薄壳。Server + SDK 交付模式是我们的差异化优势 — 让其他人能够将 AI 编码能力嵌入到自己的系统中。

---

## 📖 文档导航

| 文档 | 说明 |
|------|------|
| [🚀 快速入门](docs/QUICKSTART.md) | 从零开始，15 分钟上手 |
| [💻 CLI 使用指南](docs/CLI.md) | 命令行界面详细用法 |
| [🖥️ TUI 使用指南](docs/TUI.md) | 全屏终端界面用法 |
| [🔌 SDK 使用指南](docs/SDK.md) | Python 和 Go SDK 用法 |
| [🛠️ 技能开发指南](docs/SKILLS.md) | 创建自定义技能 |
| [⚙️ 配置文件详解](docs/CONFIG.md) | 所有配置项说明 |
| [📡 API 参考](docs/API.md) | RPC API 接口文档 |
| [🏗️ 架构设计](docs/ARCHITECTURE.md) | 系统设计和数据流 |
| [📋 功能清单](docs/FEATURES.md) | 完整功能和路线图 |
| [🤝 开发规范](CONTRIBUTING.md) | 代码规范和贡献指南 |

---

## ✨ 核心特性

### 🧠 智能思考
- **Thinking Mode** — `--thinking` 启用模型推理，可配置 token 预算
- **流式事件** — 结构化 `StreamEvent` 系统：思考、工具调用、文本增量，实时推送

### 🛠️ 强大工具
- **28 个 AI 工具** — 文件操作、搜索 (grep/glob/patch)、Shell 命令、撤销/重做、任务管理、结构化提问
- **11 个内置技能** — git、github、docker、npm、python、rust、go、java、web、cicd、testing
- **CI/CD 模板** — 开箱即用的 GitHub Actions，支持 AI 代码审查、自动修复、测试生成

### 🔌 扩展集成
- **RPC Server + SDK** — FastAPI HTTP/WebSocket 服务，Python SDK（同步 + 异步），Go SDK，可嵌入任何系统
- **MCP 集成** — 通过 stdio JSON-RPC 连接外部 MCP 服务器（GitHub、数据库等）
- **LSP 代码智能** — Python (pyright)、TypeScript (tsserver)、Go (gopls) — 诊断、跳转定义、查找引用、悬停信息

### 🤖 高级功能
- **子代理系统** — 孵化专业代理（code/research/test），asyncio 并发执行
- **上下文管理** — 接近 token 限制时自动压缩对话，智能文件分块
- **安全体系** — 工具级权限 (allow/deny/confirm)、路径遍历保护、危险命令检测、审计日志、速率限制、OAuth 2.0
- **会话持久化** — SQLite  backed 多会话管理，带历史记录

### 🌐 多模型支持
- **主流模型** — Anthropic Claude、OpenAI GPT、Google Gemini、DeepSeek
- **国内模型** — 智谱 GLM、阿里通义千问、阿里云百炼 Coding Plan
- **OpenAI 兼容** — 任何 OpenAI 兼容 API 都可通过 Pydantic AI 使用

---

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/SUT-GC/cody.git
cd cody

# 安装
pip install -e .

# 验证安装
cody --version
```

### 配置 API Key

```bash
# Anthropic（默认）
export ANTHROPIC_API_KEY='sk-ant-...'

# 或使用智谱 GLM
export CODY_MODEL='glm-4'
export CODY_MODEL_BASE_URL='https://open.bigmodel.cn/api/paas/v4/'
export CODY_MODEL_API_KEY='sk-...'

# 或阿里云百炼 Coding Plan
export CODY_MODEL='qwen3.5'
export CODY_CODING_PLAN_KEY='sk-sp-...'
```

### 第一个任务

```bash
# 初始化项目
cody init

# 执行任务
cody run "创建一个 FastAPI hello world 应用"

# 启用思考模式
cody run --thinking "设计一个用户管理 REST API"

# 指定工作目录
cody run "重构 auth.py" --workdir /path/to/project

# 交互式对话
cody chat

# 继续上次对话
cody chat --continue

# 全屏终端界面
cody tui
```

详细教程：[🚀 快速入门](docs/QUICKSTART.md)

---

## 💻 四种使用模式

### 1. CLI（命令行）

```bash
# 单次任务
cody run "refactor auth.py"
cody run --thinking "complex analysis"      # 启用思考
cody run -v "debug this"                    # 详细输出
cody run --workdir /path/to/project "fix"   # 指定工作目录

# 交互对话
cody chat                                   # REPL
cody chat --thinking                        # 启用思考
cody chat --continue                        # 继续上次
cody chat --session abc123                  # 恢复指定会话
cody chat --workdir /path/to/project        # 指定目录

# 斜杠命令：/quit, /sessions, /clear, /help
```

详细文档：[💻 CLI 使用指南](docs/CLI.md)

---

### 2. TUI（全屏终端）

```bash
cody tui                             # 全屏界面
cody tui --continue                  # 继续上次
cody tui --session <id>              # 恢复指定会话
cody tui --workdir /path/to/project  # 指定目录
```

**特性：** 流式输出、多会话管理、斜杠命令（/help, /new, /sessions, /clear）、快捷键（Ctrl+N, Ctrl+C, Ctrl+Q）

详细文档：[🖥️ TUI 使用指南](docs/TUI.md)

---

### 3. RPC Server

```bash
cody-server                          # 默认 0.0.0.0:8000
cody-server --port 9000              # 自定义端口
```

**端点：** `POST /run`, `POST /run/stream` (SSE), `POST /tool`, `GET /skills`, `GET /sessions`, `WS /ws`, `GET /audit`, `GET /health`

详细文档：[📡 API 参考](docs/API.md)

---

### 4. SDK 编程

#### Python SDK

```python
from cody import AsyncCodyClient

async with AsyncCodyClient("http://localhost:8000") as client:
    # 单次任务
    result = await client.run("create hello.py")

    # 多轮会话
    session = await client.create_session()
    await client.run("create Flask app", session_id=session.id)
    await client.run("add /health endpoint", session_id=session.id)

    # 流式输出
    async for chunk in client.stream("explain this code"):
        print(chunk.content, end="")

    # 直接调用工具
    result = await client.tool("read_file", {"path": "main.py"})
```

同步版本：`CodyClient`，内置指数退避重试。

#### Go SDK

```go
package main

import (
    cody "github.com/SUT-GC/cody-go"
    "context"
    "fmt"
)

func main() {
    client := cody.NewClient("http://localhost:8000")
    ctx := context.Background()

    // 单次任务
    result, _ := client.Run(ctx, "create hello.py")
    fmt.Println(result.Output)

    // 多轮会话
    session, _ := client.CreateSession(ctx, cody.WithTitle("My task"))
    client.Run(ctx, "create Flask app", cody.WithSession(session.ID))

    // 流式输出
    ch, _ := client.Stream(ctx, "explain this code")
    for chunk := range ch {
        fmt.Print(chunk.Content)
    }
}
```

零依赖、自动重试、上下文取消支持。

详细文档：[🔌 SDK 使用指南](docs/SDK.md)

---

## 🛠️ 工具集（28 个）

| 分类 | 工具 |
|------|------|
| **文件 I/O** | `read_file`, `write_file`, `edit_file`, `list_directory` |
| **搜索** | `grep`, `glob`, `search_files`, `patch` |
| **Shell** | `exec_command` |
| **技能** | `list_skills`, `read_skill` |
| **子代理** | `spawn_agent`, `get_agent_status`, `kill_agent` |
| **MCP** | `mcp_call`, `mcp_list_tools` |
| **Web** | `webfetch`, `websearch` |
| **LSP** | `lsp_diagnostics`, `lsp_definition`, `lsp_references`, `lsp_hover` |
| **文件历史** | `undo_file`, `redo_file`, `list_file_changes` |
| **任务管理** | `todo_write`, `todo_read` |
| **用户交互** | `question` |

---

## 🎯 技能系统（Agent Skills 开放标准）

技能遵循 [Agent Skills open standard](https://agentskills.io/) — YAML frontmatter + Markdown，已被 26+ 平台采用（Claude Code、Codex CLI、Cursor、GitHub Copilot 等）。

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

### 技能优先级

```
.cody/skills/          # 项目技能（最高优先级）
~/.cody/skills/        # 用户全局技能
{install}/skills/      # 内置技能
```

**渐进式披露：** 启动时只加载元数据（名称 + 描述）；完整指令按需加载。`<available_skills>` XML 自动注入系统提示。

**内置技能（11 个）：** `git`, `github`, `docker`, `npm`, `python`, `rust`, `go`, `java`, `web`, `cicd`, `testing`

```bash
cody skills list                     # 列出技能
cody skills show git                 # 查看技能文档
cody skills enable github            # 启用技能
cody skills disable docker           # 禁用技能
```

详细文档：[🛠️ 技能开发指南](docs/SKILLS.md)

---

## ⚙️ 配置管理

### 项目配置（`.cody/config.json`）

```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "skills": {
    "enabled": ["git", "github", "docker"]
  },
  "mcp": {
    "servers": [
      {
        "name": "github",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "..."}
      }
    ]
  },
  "permissions": {
    "overrides": {"exec_command": "allow"}
  }
}
```

### 自定义模型提供商（OpenAI 兼容 API）

```bash
# .env
CODY_MODEL=glm-4
CODY_MODEL_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
CODY_MODEL_API_KEY=sk-your-key
```

或通过 CLI 参数：

```bash
cody run "写个单元测试" --model glm-4 --model-base-url https://open.bigmodel.cn/api/paas/v4/ --model-api-key sk-xxx
```

优先级：CLI 参数 > 环境变量 > 配置文件。

### 阿里云百炼 Coding Plan

订阅 [Coding Plan](https://www.aliyun.com/benefit/scene/codingplan) 获取 Qwen3.5、GLM-5、Kimi K2.5、MiniMax M2.5 等模型的 bundled 访问。

```bash
# .env
CODY_MODEL=qwen3.5
CODY_CODING_PLAN_KEY=sk-sp-xxxxx
# 可选：对 Claude 兼容模型使用 "anthropic" 协议
# CODY_CODING_PLAN_PROTOCOL=anthropic
```

```bash
cody run "写个排序算法" --model qwen3.5 --coding-plan-key sk-sp-xxx
cody run "写单元测试" --model qwen3.5 --coding-plan-key sk-sp-xxx --coding-plan-protocol anthropic
```

支持两种协议：
- **OpenAI 兼容**（默认）：`https://coding.dashscope.aliyuncs.com/v1`
- **Anthropic 兼容**：`https://coding.dashscope.aliyuncs.com/apps/anthropic`

> 注意：Coding Plan API Key (`sk-sp-xxxxx`) 与常规 DashScope API Key (`sk-xxxxx`) 不同，不要混用。

### 配置 CLI

```bash
cody config show                     # 显示当前配置
cody config set model "anthropic:claude-sonnet-4-0"  # 设置模型
cody config set model_base_url "https://..."          # 设置 API 地址
```

详细文档：[⚙️ 配置文件详解](docs/CONFIG.md)

---

## 🧪 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试（493 个）
python3 -m pytest tests/ -v

# Lint
python3 -m ruff check cody/ tests/

# 格式化
python3 -m ruff format cody/ tests/
```

---

## 📚 文档索引

### 入门
- [🚀 快速入门](docs/QUICKSTART.md) — 15 分钟上手教程
- [💻 CLI 使用指南](docs/CLI.md) — 命令行详细用法
- [🖥️ TUI 使用指南](docs/TUI.md) — 全屏终端用法

### 开发
- [🔌 SDK 使用指南](docs/SDK.md) — Python 和 Go SDK
- [🛠️ 技能开发指南](docs/SKILLS.md) — 创建自定义技能
- [⚙️ 配置文件详解](docs/CONFIG.md) — 所有配置项说明
- [🤝 开发规范](CONTRIBUTING.md) — 代码规范和贡献指南

### 参考
- [📡 API 参考](docs/API.md) — RPC 端点、WebSocket、错误码、认证
- [🏗️ 架构设计](docs/ARCHITECTURE.md) — 系统设计、组件图、数据流
- [📋 功能清单](docs/FEATURES.md) — 完整功能列表、版本历史、竞品分析

### 其他
- [CHANGELOG.md](CHANGELOG.md) — 版本历史
- [CLAUDE.md](CLAUDE.md) — AI 助手项目指南
- [sdk/go/README.md](sdk/go/README.md) — Go SDK 文档

---

## 📄 许可证

MIT License

## 🙏 致谢

基于以下优秀项目构建：
- [Pydantic AI](https://ai.pydantic.dev/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Textual](https://textual.textualize.io/)
- [Click](https://click.palletsprojects.com/)
- [Rich](https://rich.readthedocs.io/)

---

**最后更新:** 2026-03-01 | **版本:** 1.2.0
