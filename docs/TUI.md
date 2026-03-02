# Cody - TUI 使用文档

TUI（Terminal User Interface）是 Cody 的全屏终端界面，提供比 CLI 更丰富的交互体验，支持实时流式输出、多会话管理和键盘快捷键。

---

## 快速开始

### 启动 TUI

```bash
# 基础启动
cody tui

# 指定模型
cody tui --model anthropic:claude-sonnet-4-0

# 继续上次会话
cody tui --continue

# 恢复指定会话
cody tui --session abc123

# 指定工作目录
cody tui --workdir /path/to/project
```

### 界面概览

```
┌─────────────────────────────────────────────────────────────┐
│  Cody                                          [Header]     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  You > 创建一个 Flask 应用                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Cody > 已创建 Flask 应用，包含以下文件：           │    │
│  │         - app.py: 主应用文件                        │    │
│  │         - requirements.txt: 依赖列表                │    │
│  │         → write_file(path='app.py')                 │    │
│  │         → write_file(path='requirements.txt')       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  [对话历史 - 可滚动]                                         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Session: abc123 | Model: ... | Dir: project | Msgs: 4     │
├─────────────────────────────────────────────────────────────┤
│  You > [____________________________]                       │
├─────────────────────────────────────────────────────────────┤
│  Ctrl+N New  Ctrl+C Cancel/Quit  Ctrl+Q Quit   [Footer]    │
└─────────────────────────────────────────────────────────────┘
```

---

## 界面组件

### 1. Header（顶部）

显示应用名称 "Cody"。

### 2. 对话区域（中间）

显示所有对话历史，包括：
- **用户消息** — 蓝色 "You" 标签
- **AI 回复** — 绿色 "Cody" 标签
- **系统消息** — 黄色标签（如清屏提示）
- **工具调用** — 灰色显示（如 `→ write_file(path='app.py')`）

支持上下滚动查看历史消息。

### 3. Status Line（状态行）

显示当前会话信息：
```
Session: abc123 | Model: anthropic:claude-sonnet-4-0 | Dir: project | Messages: 4
```

| 字段 | 说明 |
|------|------|
| `Session` | 当前会话 ID |
| `Model` | 使用的 AI 模型 |
| `Dir` | 工作目录名 |
| `Messages` | 消息数量 |

### 4. Input Box（输入框）

位于底部，用于输入消息或命令。

- 支持多行输入（使用反斜杠 `\` 续行）
- 支持命令历史（上下箭头）
- 支持自动补全（如果安装了 prompt_toolkit）

### 5. Footer（底部）

显示快捷键提示：
```
Ctrl+N New  Ctrl+C Cancel/Quit  Ctrl+Q Quit
```

---

## 快捷键

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| `Ctrl+N` | 新建会话 | 创建新会话，清空对话区域 |
| `Ctrl+C` | 取消/退出 | 运行时取消，空闲时退出 |
| `Ctrl+Q` | 退出 | 直接退出应用 |
| `Enter` | 发送 | 发送消息或命令 |
| `↑` / `↓` | 历史 | 浏览输入历史 |

---

## 斜杠命令

在输入框中输入 `/` 开头的命令：

### /new — 新建会话

```
/new
```

创建新会话，清空对话区域。

### /sessions — 列出会话

```
/sessions
```

显示最近 10 个会话：
```
Recent sessions:
  abc123  Flask 应用开发                      4 msgs  2026-02-28  << current
  def456  代码重构                            8 msgs  2026-02-27
  ghi789  单元测试编写                        3 msgs  2026-02-26
```

### /clear — 清屏

```
/clear
```

清空对话区域，但保留当前会话（消息仍存储在数据库中）。

### /help — 显示帮助

```
/help
```

显示所有命令和快捷键：
```
Commands:
  /new      — Start a new session
  /sessions — List recent sessions
  /clear    — Clear screen
  /quit     — Exit
  /help     — Show this help

Shortcuts:
  Ctrl+N — New session
  Ctrl+C — Cancel running / Quit
  Ctrl+Q — Quit
```

### /quit — 退出

```
/quit
```

退出 TUI 应用（同 `Ctrl+Q`）。

---

## 启动参数

### 完整参数列表

```bash
cody tui \
  --model <模型名称> \
  --model-base-url <API 地址> \
  --model-api-key <API Key> \
  --coding-plan-key <阿里云 Coding Plan Key> \
  --coding-plan-protocol <openai|anthropic> \
  --thinking/--no-thinking \
  --thinking-budget <token 数> \
  --workdir <工作目录> \
  --session <会话 ID> \
  --continue
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--model` | AI 模型名称 | 配置文件中的模型 |
| `--model-base-url` | 自定义 OpenAI 兼容 API 地址 | - |
| `--model-api-key` | 自定义模型 API Key | - |
| `--coding-plan-key` | 阿里云百炼 Coding Plan Key | - |
| `--coding-plan-protocol` | Coding Plan 协议类型 | `openai` |
| `--thinking` | 启用思考模式 | 配置文件设置 |
| `--thinking-budget` | 思考 token 预算 | - |
| `--workdir` | 工作目录 | 当前目录 |
| `--session` | 恢复指定会话 | - |
| `--continue` | 继续上次会话 | `false` |

### 使用示例

```bash
# 使用不同模型
cody tui --model glm-4 --model-base-url https://open.bigmodel.cn/api/paas/v4/

# 启用思考模式
cody tui --thinking --thinking-budget 10000

# 指定工作目录
cody tui --workdir /path/to/project

# 恢复会话
cody tui --session abc123
cody tui --continue
```

---

## 使用场景

### 场景 1：多轮对话开发

```bash
# 启动 TUI
cody tui --workdir /path/to/project

# 第一轮：创建项目
You > 创建一个 FastAPI 项目

# 第二轮：添加功能
You > 添加用户认证模块

# 第三轮：修复问题
You > 修复登录接口的 bug

# 第四轮：优化代码
You > 重构数据库连接池
```

### 场景 2：会话切换

```bash
# 查看历史会话
You > /sessions

# 切换到另一个会话
You > /new

# 开始新任务
You > 帮我分析这个项目的架构问题
```

### 场景 3：实时调试

```bash
# 启用详细模式（显示工具调用）
cody tui --thinking

# 观察 AI 的思考过程和工具调用
You > 为什么这个测试失败了？

# 看到 AI 逐步分析：
# - 读取测试文件
# - 读取源代码
# - 执行测试命令
# - 分析错误信息
```

---

## 会话管理

### 会话持久化

所有会话自动保存到 `~/.cody/sessions.db`（SQLite 数据库）。

### 会话恢复

```bash
# 自动恢复上次会话
cody tui --continue

# 恢复指定会话
cody tui --session abc123
```

### 会话信息

每个会话包含：
- `id` — 会话 ID（12 位十六进制）
- `title` — 会话标题（自动从第一条消息生成）
- `model` — 使用的模型
- `workdir` — 工作目录
- `messages` — 对话历史
- `created_at` — 创建时间
- `updated_at` — 最后更新时间

---

## 流式输出

TUI 实时显示 AI 的响应过程：

### 思考过程（如果启用）

```
Cody > [dim]让我先分析一下这个项目的结构...
       我需要查看目录结构和主要文件...[/dim]
```

### 工具调用

```
Cody > → read_file(path='main.py')
       → grep(pattern='def main', include='*.py')
```

### 文本输出

```
Cody > 已创建 FastAPI 项目，包含以下文件：
       - main.py: 主应用文件
       - requirements.txt: 依赖列表
```

---

## 与 CLI 对比

| 特性 | TUI | CLI Chat |
|------|-----|----------|
| 界面 | 全屏终端 | REPL 行式 |
| 快捷键 | ✅ 丰富 | ❌ 有限 |
| 会话切换 | ✅ `/new` | ✅ `/new` |
| 清屏 | ✅ `/clear` | ✅ `/clear` |
| 实时流式 | ✅ 平滑 | ✅ 行式 |
| 工具调用显示 | ✅ 内联 | ✅ 内联 |
| 鼠标支持 | ✅ Textual 支持 | ❌ |
| 后台运行 | ❌ | ❌ |

---

## 常见问题

### Q: TUI 卡住了怎么办？

按 `Ctrl+C` 取消当前操作，或 `Ctrl+Q` 退出应用。

### Q: 如何查看完整的工具调用结果？

TUI 默认简化显示工具调用。如需详细输出，使用 CLI 的 `-v` 模式：
```bash
cody run -v "任务"
```

### Q: 会话存储在哪里？

`~/.cody/sessions.db`

### Q: 如何删除会话？

使用 CLI：
```bash
cody sessions delete abc123
```

### Q: TUI 显示乱码怎么办？

确保终端支持 UTF-8：
```bash
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

### Q: 如何调整 TUI 主题？

TUI 使用 Textual 的默认主题。可以通过 Textual 的配置自定义主题（高级用法）。

---

## 高级用法

### 1. 多行输入

使用反斜杠续行：
```
You > 帮我创建一个 FastAPI 应用，\
      包含用户认证、数据库连接、\
      和 JWT token 验证
```

### 2. 命令历史

使用上下箭头浏览输入历史。

### 3. 后台运行（不推荐）

TUI 设计为前台交互应用。如需后台运行，使用 Python SDK（in-process，无需启动 Server）：
```python
from cody import AsyncCodyClient

async with AsyncCodyClient() as client:
    result = await client.run("任务")
```

---

## 技术细节

### 框架

TUI 基于 [Textual](https://textual.textualize.io/) 构建。

### Widget 结构

```
App (CodyTUI)
├── Header
├── VerticalScroll (#chat-scroll)
│   ├── MessageBubble (user)
│   ├── MessageBubble (assistant)
│   └── StreamBubble (streaming)
├── StatusLine (#status-line)
├── Input (#prompt-input)
└── Footer
```

### 数据流

```
用户输入 → on_input_submitted() → _run_agent() → AgentRunner.run_stream()
                                            ↓
StreamEvent → ThinkingEvent/TextDeltaEvent/ToolCallEvent/DoneEvent
                                            ↓
StreamBubble.append() → 实时更新 UI
```

---

## 最佳实践

### 1. 使用工作目录

始终明确指定工作目录：
```bash
cody tui --workdir /path/to/project
```

### 2. 合理新建会话

不同任务使用不同会话，便于管理：
```
You > /new  # 新任务开始
```

### 3. 使用思考模式分析复杂问题

```bash
cody tui --thinking "分析项目架构问题"
```

### 4. 定期清理会话

使用 CLI 删除不需要的会话：
```bash
cody sessions delete abc123
```

---

## 与 Server 的关系

TUI 直接使用核心引擎（in-process），不需要启动 Server。Web（`cody-web`）是独立的 Web + RPC 服务，供外部系统通过 HTTP/WebSocket 调用。

```bash
# TUI — 直接使用核心引擎
cody tui

# Web — 供外部系统调用（端口 8000）
cody-web
```

---

**最后更新:** 2026-02-28
