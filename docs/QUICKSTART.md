# Cody - 快速入门

欢迎使用 Cody！本教程带你在 15 分钟内上手，覆盖 SDK 嵌入和 CLI 直接使用两种方式。

---

## 1. 安装

### 系统要求

- Python 3.10+
- pip 包管理器

### 选择安装方式

```bash
# 只用 SDK（最轻量，4 个依赖）
pip install cody-ai

# 用 CLI 交互
pip install cody-ai[cli]

# 全部功能（CLI + TUI + Web）
pip install cody-ai[all]

# 从源码安装（开发）
git clone https://github.com/CodyCodeAgent/cody.git
cd cody
pip install -e ".[dev]"
```

---

## 2. 配置模型

Cody 支持多种模型提供商，你需要先配置 API Key。

### 方式 1：交互式配置（推荐）

```bash
cody config setup
```

### 方式 2：环境变量

```bash
# Anthropic Claude
export CODY_MODEL_API_KEY='sk-ant-...'

# 智谱 GLM
export CODY_MODEL='glm-4'
export CODY_MODEL_BASE_URL='https://open.bigmodel.cn/api/paas/v4/'
export CODY_MODEL_API_KEY='sk-...'

# 阿里云百炼 Coding Plan
export CODY_MODEL='qwen3.5'
export CODY_CODING_PLAN_KEY='sk-sp-...'
```

### 验证配置

```bash
cody config show
```

---

## 3. SDK 快速上手

SDK 是 Cody 框架的核心接入方式，直接调用引擎（in-process），无需启动任何服务。

### 3.1 第一个任务

```python
import asyncio
from cody import AsyncCodyClient

async def main():
    async with AsyncCodyClient(workdir="/tmp/myproject") as client:
        result = await client.run("创建一个 Python 脚本，打印 Hello World")
        print(result.output)

asyncio.run(main())
```

### 3.2 多轮对话

```python
async with AsyncCodyClient(workdir="/tmp/myproject") as client:
    session = await client.create_session(title="Flask 开发")

    r1 = await client.run("创建一个 Flask 应用", session_id=session.id)
    print(r1.output)

    r2 = await client.run("添加 /health 端点", session_id=session.id)
    print(r2.output)

    r3 = await client.run("编写 pytest 测试", session_id=session.id)
    print(r3.output)
```

### 3.3 流式输出

```python
async with AsyncCodyClient() as client:
    async for chunk in client.stream("分析这个项目的架构"):
        if chunk.type == "text_delta":
            print(chunk.content, end="", flush=True)
        elif chunk.type == "tool_call":
            print(f"\n  → {chunk.content}")
        elif chunk.type == "done":
            print("\n完成")
```

### 3.4 Builder 模式

```python
from cody import Cody

client = (
    Cody()
    .workdir("/path/to/project")
    .model("claude-sonnet-4-0")
    .thinking(enabled=True, budget=10000)
    .enable_metrics()
    .enable_events()
    .build()
)

async with client:
    result = await client.run("重构 auth 模块")
    print(client.get_metrics())  # Token 使用统计
```

### 3.5 同步版本

```python
from cody import CodyClient

with CodyClient(workdir="/tmp/myproject") as client:
    result = client.run("创建 hello.py")
    print(result.output)
```

更多 SDK 用法：[SDK 使用指南](SDK.md)

---

## 4. CLI 快速上手

CLI 是 Cody 的命令行界面，适合终端中快速执行任务。

### 4.1 初始化项目

```bash
cd ~/myproject
cody init    # 创建 .cody/ 配置目录和 CODY.md 项目说明
```

### 4.2 执行任务

```bash
# 基础任务
cody run "创建一个 FastAPI 项目，包含 / 和 /health 端点"

# 启用思考模式（显示推理过程）
cody run --thinking "设计一个用户管理 REST API"

# 指定工作目录
cody run --workdir /path/to/project "修复测试失败"

# 详细输出（显示工具调用结果）
cody run -v "读取并分析 main.py"
```

### 4.3 交互式对话

```bash
# 启动对话
cody chat

# 继续上次对话
cody chat --continue

# 恢复指定会话
cody chat --session abc123
```

**斜杠命令：** `/quit` 退出, `/sessions` 列出会话, `/clear` 清屏, `/help` 帮助

### 4.4 会话管理

```bash
cody sessions list              # 列出会话
cody sessions show <id>         # 查看会话
cody sessions delete <id>       # 删除会话
```

### 4.5 技能管理

```bash
cody skills list                # 列出所有技能
cody skills show git            # 查看技能文档
cody skills enable github       # 启用技能
cody skills disable docker      # 禁用技能
```

更多 CLI 用法：[CLI 使用指南](CLI.md)

---

## 5. TUI 全屏终端

```bash
cody tui                        # 启动全屏界面
cody tui --continue             # 继续上次会话
cody tui --workdir /path        # 指定工作目录
```

**快捷键：** `Ctrl+N` 新会话, `Ctrl+C` 取消/退出, `Ctrl+Q` 退出

更多 TUI 用法：[TUI 使用指南](TUI.md)

---

## 6. Web 界面

```bash
cody-web --dev                  # 开发模式（Vite HMR + FastAPI）
cody-web --port 8000            # 生产模式
```

**功能：** 项目管理、实时对话、图片上传、深色主题

**API 端点：** `POST /run`, `POST /run/stream` (SSE), `POST /tool`, `GET /skills`, `GET /sessions`, `WS /ws`

更多 Web/API 用法：[API 参考](API.md)

---

## 7. 定制你的 Agent

### 7.1 自定义 Skills

在 `.cody/skills/` 下创建你自己的技能：

```bash
mkdir -p .cody/skills/my-skill
cat > .cody/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: 我的自定义编码规范
---

# 项目编码规范

- 使用 4 空格缩进
- 函数名使用 snake_case
- 所有公开函数必须有 docstring
EOF

# 验证
cody skills list
```

### 7.2 连接 MCP 服务器

在 `.cody/config.json` 中配置：

```json
{
  "mcp": {
    "servers": [
      {
        "name": "github",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": { "GITHUB_TOKEN": "..." }
      }
    ]
  }
}
```

### 7.3 权限控制

```json
{
  "permissions": {
    "overrides": {
      "exec_command": "allow",
      "write_file": "confirm"
    }
  }
}
```

---

## 8. 下一步

| 目标 | 文档 |
|------|------|
| 深入了解 SDK | [SDK 使用指南](SDK.md) |
| 创建自定义技能 | [技能开发指南](SKILLS.md) |
| 理解框架架构 | [架构设计](ARCHITECTURE.md) |
| 了解全部配置项 | [配置文件详解](CONFIG.md) |
| 参与贡献 | [开发规范](../CONTRIBUTING.md) |

---

**最后更新:** 2026-03-04
