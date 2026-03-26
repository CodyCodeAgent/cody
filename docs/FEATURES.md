# Cody - 功能与特性

## 概述

Cody 是一个**开源 AI Coding Agent 框架**，提供构建 AI 编程代理所需的完整基础设施：多模型支持、28 个内置工具、Agent Skills 开放标准、子 Agent 编排、MCP 集成，以及 CLI/TUI/Web/SDK 四种运行方式。

开源地址：[https://github.com/CodyCodeAgent/cody](https://github.com/CodyCodeAgent/cody.git)

## 核心定位

> **Cody 是一个完整的 AI Coding Agent 框架——核心引擎（core）实现所有功能逻辑，CLI、Web、TUI 是参考实现，SDK 让你用几行代码构建自己的 AI 编程工具。**
> 引擎做厚，壳子做薄。框架完整度是核心竞争力。

**目标用户：**
- **团队/公司构建 AI 编程工具** — 通过 Python SDK 或 HTTP API 将 Cody 框架集成到自己的产品中（**核心场景**）
- **开发者定制 AI Agent** — 通过 Agent Skills 标准和 MCP 集成，快速定制专属 AI 编程代理
- **个人程序员** — 通过 CLI/TUI/Web 直接使用，同时也是框架最好的 dogfooding 方式

**核心价值：**
- **框架完整度** — 从工具调用到子 Agent 编排，从会话管理到安全审计，开箱即用
- **Agent Skills 开放标准** — 兼容 Anthropic 发布的 Agent Skills 标准，已被 26+ 平台采纳
- **多模型支持** — Anthropic、OpenAI、Google、DeepSeek、阿里通义千问、智谱 GLM 等
- **开源可控** — 完整源码，自由定制，数据留在本地

---

## 功能清单

### 1. 核心 AI 能力

**基于 Pydantic AI 构建：**
- 多模型支持（Anthropic、OpenAI、Google、DeepSeek 等）
- 自定义 OpenAI 兼容 API 支持（智谱 GLM、阿里通义千问/DashScope 等）
- 多模态输入 — 支持文本+图片混合提示（Web 端），通过 `Prompt` 类型和 pydantic-ai `BinaryContent` 传递
- 结构化输出
- 工具调用（Function Calling）
- 流式响应（结构化 StreamEvent：thinking / tool_call / tool_result / text_delta / done / cancelled / circuit_breaker / interaction_request / user_input_received）
- 熔断器（Circuit Breaker）— token/cost 上限 + 死循环检测，自动终止失控 Agent
- 人工交互层（Human-in-the-Loop）— AI 主动提问 + 用户随时输入，双向互动
- 跨任务记忆（Project Memory）— AI 自动积累项目经验，注入后续会话 system prompt
- 结构化输出（TaskMetadata）— 自动提取 summary、confidence、issues、next_steps
- 会话管理（SQLite 持久化）
- Thinking 模式（`--thinking` 开启，`--thinking-budget` 控制 token 预算）

**认证方式：**
- API Key（通过交互式配置向导 `cody config setup` 设置）
- 支持 OpenAI 兼容 API（`model_base_url` + `model_api_key`）
- 多模型配置

### 2. 内置工具集（29 个）

**文件操作：**
- `read_file(path)` - 读取文件
- `write_file(path, content)` - 写入文件
- `edit_file(path, old_text, new_text)` - 精确编辑
- `list_directory(path)` - 列出目录
- `search_files(pattern, path)` - 搜索文件

**搜索工具：**
- `grep(pattern, path, include)` - 正则搜索文件内容
- `glob(pattern, path)` - 模式匹配查找文件
- `search_files(query, path)` - 模糊文件名搜索
- `patch(path, diff)` - 应用 unified diff 补丁

**命令执行：**
- `exec_command(command)` - 执行 Shell 命令（支持白名单和危险命令检测）

**工具错误自动重试：**
- 工具执行失败（如 `edit_file` 找不到目标文本、`read_file` 文件不存在）时，错误信息自动返回给 AI 模型
- AI 可以根据错误信息修正参数后重试（最多 2 次重试）
- 捕获 `ToolError`（`ToolInvalidParams` / `ToolPathDenied` / `ToolPermissionDenied`）和 `FileNotFoundError`
- 基于 pydantic-ai 的 `ModelRetry` 机制，不会打断整个对话流

**任务管理：**
- `todo_write(todos)` - 创建/更新任务清单
- `todo_read()` - 读取当前任务清单

**用户交互：**
- `question(text, options)` - 向用户提结构化选择题

**记忆：**
- `save_memory(category, content)` - AI 主动保存跨任务经验（conventions/patterns/issues/decisions）

**Skill 元工具：**
- `list_skills()` — 列出可用 Skills（只返回元数据，渐进式加载）
- `read_skill(name)` — 加载 Skill 完整指令（按需激活）
- System prompt 自动注入 `<available_skills>` XML，AI 按上下文匹配

**自定义工具注册：**
- 通过 SDK Builder `.tool(func)` 注册自定义 async 工具函数
- 自定义工具与内置工具享有相同的错误重试和输出截断机制
- 工具签名：`async def my_tool(ctx: RunContext[CodyDeps], arg: str) -> str`

### 3. Skill 系统（Agent Skills 开放标准）

> 完全兼容 [Agent Skills 开放标准](https://agentskills.io/) — Anthropic 发布，已被 Claude Code、GitHub Copilot、Codex CLI、Cursor 等 26+ 平台采纳。

**SKILL.md 格式（YAML frontmatter + Markdown）：**
```markdown
---
name: git
description: Git version control operations. Use when working with git repositories.
metadata:
  author: cody
  version: "1.0"
---
# Git Operations
Instructions for the AI agent...
```

**目录结构（标准）：**
```
skill-name/
├── SKILL.md          # 必须 — YAML frontmatter + Markdown 指令
├── scripts/          # 可选 — 可执行脚本
├── references/       # 可选 — 补充文档
└── assets/           # 可选 — 模板、数据文件
```

**两层优先级加载：**
```
.cody/skills/          # 项目 Skills（最高优先级）
~/.cody/skills/        # 全局 Skills
```

> v1.11.0 起不再提供内置 Skills，鼓励用户按项目需求创建自定义 Skills。Skill 基础设施（SkillManager、渐进式加载、system prompt 注入）保持不变。

**渐进式加载（Progressive Disclosure）：**
1. 启动时 — 只解析 YAML frontmatter（name + description）
2. 激活时 — 加载完整 SKILL.md body
3. 按需 — 读取 scripts/、references/、assets/

**Skill 管理命令：**
```bash
cody skills list                  # 列出可用 Skills
cody skills enable <name>         # 启用 Skill
cody skills disable <name>        # 禁用 Skill
```

**自定义 Skill 目录：**
- 通过 `config.json` 的 `skills.custom_dirs` 或环境变量 `CODY_SKILL_DIRS` 配置额外搜索目录
- SDK Builder 支持 `.skill_dir(path)` / `.skill_dirs(paths)` 方法
- 优先级：custom > project > global > builtin

### 4. MCP 集成

**支持方式：**
- 作为 MCP Client 连接外部 MCP Servers
- **双传输模式**：stdio（本地子进程）和 HTTP（远程端点）
- 配置化管理 + SDK 动态添加
- AI Agent 自动感知 MCP 工具（动态系统提示注入）

**stdio 传输（本地子进程）：**
```json
{
  "mcp": {
    "servers": [
      {
        "name": "github",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": { "GITHUB_TOKEN": "..." }
      }
    ]
  }
}
```

**HTTP 传输（远程端点，v1.9.0+）：**
```json
{
  "mcp": {
    "servers": [
      {
        "name": "feishu",
        "transport": "http",
        "url": "https://mcp.feishu.cn/mcp",
        "headers": { "X-Lark-MCP-UAT": "your-token" }
      }
    ]
  }
}
```

**SDK 集成（v1.9.0+）：**
```python
from cody.sdk import Cody

client = (
    Cody()
    .mcp_http_server("feishu", url="https://mcp.feishu.cn/mcp", headers={...})
    .mcp_stdio_server("github", command="npx", args=["-y", "@modelcontextprotocol/server-github"])
    .auto_start_mcp(True)
    .build()
)

async with client:
    result = await client.run("总结飞书文档")

    # 运行时动态添加
    await client.add_mcp_server(name="db", command="npx", args=[...])
```

**常用 MCP Servers：**

- GitHub Server（stdio）
- Database Server（stdio）
- Filesystem Server（stdio）
- 飞书/Lark Server（HTTP）
- Web Search Server（stdio/HTTP）

### 5. 子 Agent 系统

**功能：**
- 主 Agent 可以孵化子 Agent 处理特定任务
- 子 Agent 独立运行，完成后返回结果
- 支持不同类型的子 Agent（编码、研究、测试等）

**工具：**
- `spawn_agent(task, type)` - 孵化子 Agent
- `get_agent_status(agent_id)` - 查询子 Agent 状态
- `kill_agent(agent_id)` - 终止子 Agent
- `resume_agent(agent_id)` - 恢复已完成/失败/超时的子 Agent（携带原始任务 + 前次输出/错误作为上下文）

**使用场景：**
- 复杂任务分解
- 并行处理多个子任务
- 专门化处理（编码/研究/测试分离）
- 失败/超时后恢复继续

### 6. 框架能力：四种运行方式 + SDK

Cody 框架提供同一核心引擎的多种接入方式，适用于不同场景：

#### Python SDK（框架核心接入方式）

**安装：**
```bash
pip install cody-ai            # 仅安装核心 SDK（4 个依赖）
pip install cody-ai[cli]       # 含 CLI
pip install cody-ai[all]       # 全部功能
```

**基本使用：**
```python
from cody import Cody

# Builder 模式创建客户端
client = Cody().workdir("/path/to/project").model("claude-sonnet-4-0").build()

# 同步执行
result = client.run("重构 auth.py，提取通用逻辑到 utils.py")
print(result.output)
print(result.usage)

# 流式执行
for event in client.stream("创建一个 FastAPI 项目"):
    if event.type == "text_delta":
        print(event.content, end="")

# 会话管理
session = client.create_session()
result = client.run("第一步：分析代码", session_id=session.id)
result = client.run("第二步：重构", session_id=session.id)

# 直接调用工具
result = client.tool("read_file", {"path": "README.md"})
```

**异步客户端：**
```python
from cody import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/path/to/project")
    result = await client.run("分析代码质量")
    async for event in client.stream("修复所有 lint 警告"):
        print(event)
```

**事件系统：**
```python
from cody import Cody

client = Cody().build()

@client.events.on("tool_call")
def on_tool(event):
    print(f"调用工具: {event.tool_name}")

@client.events.on("done")
def on_done(event):
    print(f"Token 使用: {event.usage}")
```

**SDK 特性：**
- `CodyClient`（同步）+ `AsyncCodyClient`（异步）双客户端
- Builder 模式 — 链式配置创建客户端
- 事件系统 — `EventManager` 同步/异步事件分发
- 指标采集 — `MetricsCollector` 记录 token 使用、工具调用统计
- 10 种错误类型 — `CodyError` → `CodyAuthError` / `CodyModelError` / `CodyToolError` 等
- In-process 调用 — 直接包装核心引擎，无需 HTTP，零额外延迟

#### HTTP API（远程集成）

启动 HTTP 服务：
```bash
cody-web                  # 生产模式
cody-web --dev            # 开发模式（含 Vite HMR）
cody-web --port 9000      # 指定端口
```

**API 接口：**

**POST /run**
```json
{
  "prompt": "创建 hello.py",
  "workdir": "/path/to/project",
  "skills": ["python", "git"],
  "stream": false
}

// 响应
{
  "output": "已创建 hello.py",
  "usage": {
    "input_tokens": 100,
    "output_tokens": 50
  }
}
```

**POST /run/stream**
```json
{
  "prompt": "创建项目"
}

// SSE 流式响应（结构化事件）
data: {"type": "thinking", "content": "Let me create..."}
data: {"type": "tool_call", "tool_name": "write_file", "args": {"path": "main.py"}, "tool_call_id": "tc_1"}
data: {"type": "tool_result", "tool_name": "write_file", "tool_call_id": "tc_1", "result": "Written 200 bytes"}
data: {"type": "text_delta", "content": "项目已创建"}
data: {"type": "done", "output": "项目已创建", "thinking": "...", "tool_traces": [...]}
```

**POST /tool**
```json
{
  "tool": "read_file",
  "params": {
    "path": "README.md"
  }
}

// 响应
{
  "result": "# Project Name\n..."
}
```

**GET /skills**
```json
{
  "skills": [
    {
      "name": "github",
      "enabled": true,
      "source": "project"
    }
  ]
}
```

**GET /health**
```json
{
  "status": "ok",
  "version": "1.7.0"
}
```

#### CLI 模式（参考实现）

```bash
# 初始化项目
cody init

# 单次执行
cody run "创建一个 FastAPI 项目"
cody run --thinking "复杂分析任务"
cody run -v "调试这个问题"

# 交互对话
cody chat
cody chat --continue
cody chat --session <id>

# 配置管理
cody config setup                  # 交互式配置向导
cody config show                   # 查看配置
cody config set model <value>      # 设置模型
```

#### TUI 模式（参考实现）

**全屏交互终端（基于 Textual）：**
```bash
cody tui                     # 启动 TUI
cody tui --continue          # 继续上次会话
cody tui --session <id>      # 恢复指定会话
```

**功能：**
- 流式响应实时显示
- 多会话管理（新建/恢复/列出/切换）
- 斜杠命令（/help, /new, /sessions, /clear, /quit）
- 键盘快捷键（Ctrl+N 新会话, Ctrl+C 取消/退出, Ctrl+Q 退出）
- 状态栏处理状态指示器 — 显示 "Thinking..." -> "Running {tool}..." -> "Generating..." + 实时耗时

#### Web 前端（参考实现）

独立 Web 应用，遵循"引擎做厚，壳子做薄"理念。

**架构：** `React (Vite:5173) -> Web Backend (FastAPI:8000, web.db) -> Core Engine`

**功能：**
- 项目管理 — 创建/编辑/删除项目（名称、描述、工作目录）
- 项目向导 — 目录浏览器选择 workdir，自动初始化 `.cody/`
- 实时对话 — WebSocket 流式消息显示
- 图片上传 — 支持粘贴截图（Ctrl+V）和文件选择，图片随消息发送到多模态模型
- 流式状态栏 — 显示处理状态（Thinking/Running/Generating）+ 耗时 + Stop 按钮
- WebSocket 断连恢复 — 断连时自动重置 streaming 状态并提示用户
- 空闲超时 — 120 秒无事件自动停止，防止永久卡住
- GFM Markdown 渲染 — 支持表格、任务列表、删除线等（`remark-gfm`）
- 项目侧边栏 — 快速切换/删除项目
- 深色主题 UI

### 7. 项目配置

**`.cody/config.json`（项目级）：**
```json
{
  "model": "claude-sonnet-4-0",
  "skills": {
    "enabled": ["github", "docker"],
    "disabled": ["web"]
  },
  "mcp": {
    "servers": [...]
  },
  "tools": {
    "shell": {
      "allowed_commands": ["git", "npm", "docker"]
    }
  }
}
```

**`~/.cody/config.json`（全局）：**
```json
{
  "model_api_key": "sk-...",
  "default_model": "claude-sonnet-4-0",
  "skills": {
    "enabled": ["git"]
  }
}
```

**模型认证方式（优先级从高到低）：**

| 方式 | 配置 | 说明 |
|------|------|------|
| 交互式配置 | `cody config setup` | 推荐方式，引导配置并保存 |
| OpenAI 兼容 API | `model_base_url` + `model_api_key` | 智谱 GLM、阿里 DashScope 等 |
| API Key | `model_api_key`（通过 `cody config setup` 配置） | 可选 |

### 8. 安全特性

**命令执行限制：**

- 白名单机制（`security.allowed_commands`，管道/链式命令逐段检查）
- 危险命令拦截（内置 `rm -rf /`、`dd if=`、`:(){` 底线拦截）
- 可扩展黑名单（`security.blocked_commands`，SDK 用户按需自定义）
- 需要确认的操作

**权限管理：**

- 文件访问限制（在项目目录内）
- 严格读边界模式（`strict_read_boundary`，限制读操作也遵守访问边界）
- 网络访问控制
- 子 Agent 资源限制

**审计日志：**
- 记录所有命令执行
- 记录文件修改
- 记录 API 调用

### 9. 熔断器（Circuit Breaker）

防止 Agent 失控运行，自动终止异常任务：

**三种触发条件：**
- **Token 上限** — 累计 token 超过 `max_tokens`（默认 200,000）
- **Cost 上限** — 预估成本超过 `max_cost_usd`（默认 $5.0）
- **死循环检测** — 连续 N 轮工具返回高度相似结果（SequenceMatcher 相似度 ≥ 0.9）

**配置：**
```json
{
  "circuit_breaker": {
    "enabled": true,
    "max_tokens": 200000,
    "max_cost_usd": 5.0,
    "max_steps": 0,
    "loop_detect_turns": 6,
    "loop_similarity_threshold": 0.9
  }
}
```

**SDK：**
```python
client = Cody().circuit_breaker(max_cost_usd=10.0, max_tokens=500000).build()
```

触发时，流式模式 yield `CircuitBreakerEvent`（reason/tokens_used/cost_usd），同步模式抛出 `CircuitBreakerError`。

### 10. 人工交互（Human-in-the-Loop）

**两种模式共存：**

1. **AI 主动提问** — `question` 工具 + `InteractionRequest/Response` 机制，AI 发起请求等待人类回答
2. **用户随时输入** — `UserInputQueue` + `inject_user_input()`，用户在 Agent 运行中主动发送消息，消息在下一个 node 边界注入（通过 `CallToolsNode.user_prompt`），LLM 在下一轮看到

**SDK：**
```python
# AI 主动提问模式
client = Cody().interaction(enabled=True, timeout=30).build()
async for chunk in client.stream("分析代码"):
    if chunk.type == "interaction_request":
        await client.submit_interaction(chunk.request_id, action="answer", content="继续")

# 用户随时输入模式
await client.inject_user_input("停下来，先处理这个 bug")
```

**CLI / TUI / Web 全面支持：**
- **CLI** — `interaction_request` 事件自动提示用户输入，支持选项选择
- **TUI** — 交互请求显示在对话气泡中，用户在输入框回答
- **Web** — 黄色交互卡片显示问题，支持选项按钮快捷回答或文本输入

**WebSocket：**
```json
// 用户主动输入
{"type": "user_input", "content": "先处理这个紧急 bug"}
// AI 提问后回答
{"type": "submit_interaction", "request_id": "abc123", "action": "answer", "content": "Python"}
```

### 11. 跨任务记忆（Project Memory）

AI 自动积累项目经验，跨会话复用：

**四个分类：**
- `conventions` — 代码规范、命名约定、工具偏好
- `patterns` — 设计模式、常用工具函数、项目惯用法
- `issues` — 已知 Bug、边界条件、踩坑记录
- `decisions` — 架构决策、技术选型、理由

**存储：** `~/.cody/memory/<project_hash>/` 下每分类一个 JSON 文件，最多 50 条/分类

**AI 自动保存：** `save_memory` 工具让 AI 在任务中主动记录发现的重要信息

**自动注入：** 记忆内容自动注入到后续会话的 system prompt（`## Project Memory` 段）

**SDK：**
```python
await client.add_memory("conventions", "测试文件用 test_ 前缀，放在 tests/ 目录")
memories = await client.get_memory()
await client.clear_memory()
```

---

## 技术架构

**核心技术栈：**
- Python 3.10+
- Pydantic AI（Agent 框架）
- FastAPI（HTTP API + Web Backend）
- Click（CLI）
- Textual（TUI）
- Rich（终端渲染）

**模型支持：**
- Anthropic Claude（推荐）
- OpenAI GPT
- Google Gemini
- DeepSeek
- 阿里通义千问（DashScope）
- 智谱 GLM
- 其他兼容 OpenAI API 的模型

---

## 使用场景

### 1. 通过 SDK 构建 AI 编程工具

```python
from cody import Cody

# 构建自己的 AI 代码审查系统
client = Cody().workdir(repo_path).model("claude-sonnet-4-0").build()

# 自动代码审查
diff = get_pr_diff()
result = client.run(f"审查以下代码变更，给出改进建议：\n{diff}")
post_review_comment(result.output)

# 自动修复 Issue
issue = get_github_issue(issue_id)
result = client.run(f"修复这个问题：{issue.title}\n{issue.body}")
create_pr(result.output)
```

### 2. HTTP API 集成

```javascript
// 在你的应用中集成 Cody
const response = await fetch('http://localhost:8000/run', {
  method: 'POST',
  body: JSON.stringify({
    prompt: '创建一个 API 路由',
    workdir: '/path/to/project'
  })
});
```

### 3. CI/CD 自动化

```yaml
# .github/workflows/ai-review.yml
- name: AI Code Review
  run: |
    cody run "检查代码质量并生成报告" > review.md
```

### 4. CLI 直接使用

```bash
cd ~/myproject
cody init
cody run "帮我重构 auth.py，提取通用逻辑到 utils.py"
```

### 5. 多项目管理

```bash
# 项目 A 有自己的 skills
cd ~/project-a
cody run "使用项目 A 的配置"

# 项目 B 有不同的 skills
cd ~/project-b
cody run "使用项目 B 的配置"
```

---

## 路线图

### v0.1.0 — 框架原型 ✅ 已完成
- [x] 基础 Agent 框架（Pydantic AI）
- [x] 核心工具（read_file, write_file, edit_file, list_directory, exec_command）
- [x] CLI 参考实现（run, init, skills, config）
- [x] 项目配置支持（全局/项目级 config.json）
- [x] Skill 系统基础（三层加载、SKILL.md、enable/disable）
- [x] HTTP API 骨架（FastAPI, /run, /run/stream, /tool, /skills, /health）

### v0.2.0 — 工具与会话 ✅ 已完成
- [x] 搜索工具（grep, glob, search_files）— 正则搜索、模式匹配、模糊文件名搜索
- [x] patch 工具 — 应用 unified diff 补丁
- [x] 搜索准确度对齐 ripgrep — 二进制文件检测、.gitignore 支持、默认忽略目录
- [x] 路径遍历安全修复 — resolve() 防止 symlink 逃逸
- [x] SQLite 会话持久化 — 对话历史存储、多会话管理
- [x] CLI 交互模式 — `cody chat`、`--continue`、`--session`
- [x] 81 个单元测试，ruff 零告警

### v0.3.0 — 框架化 ✅ 已完成

> **本阶段目标：把 Cody 从原型变成可集成的 AI Coding Agent 框架。**

**P0：HTTP API 完善**
- [x] Session API — `POST /sessions`, `GET /sessions`, `GET /sessions/:id`, `DELETE /sessions/:id`
- [x] 带会话的对话 — `POST /run` 支持 `session_id` 参数，自动持久化对话历史
- [x] SSE 结构化 JSON 事件 — `{type: text/done/error}`
- [x] API 完整测试 — 32+ 个端点测试
- [x] Runner + Session 打通 — `run_with_session` / `run_stream_with_session`
- [x] 结构化错误响应 — 统一 `ErrorCode` 枚举、`CodyAPIError`、`{"error": {"code", "message", "details"}}` 格式
- [x] WebSocket 双向通信 — `WS /ws` 端点，支持 run/cancel/ping，实时流式推送
- [x] Sub-Agent API — `POST /agent/spawn`, `GET /agent/:id`, `DELETE /agent/:id`

**P0：Python SDK**
- [x] `CodyClient` / `AsyncCodyClient` — 同步 + 异步双客户端
- [x] 核心方法 — `run()`, `stream()`, `tool()`, `health()`
- [x] 会话管理 — `create_session()`, `list_sessions()`, `get_session()`, `delete_session()`
- [x] 错误处理 — `CodyError`, `CodyNotFoundError`
- [x] In-process 封装 — 直接调用核心引擎，无需 HTTP 连接
- [x] 22 个 SDK 测试

**P1：MCP Client 集成**
- [x] `MCPClient` 实现 — stdio JSON-RPC 协议，管理 MCP Server 子进程
- [x] 从配置文件加载 MCP Server — `MCPConfig.servers` 自动启动
- [x] MCP Server 生命周期管理 — `start_all()` / `stop_all()` / `restart_server()`
- [x] MCP 工具自动注册到 Agent — `mcp_call()` / `mcp_list_tools()` 工具
- [x] 工具发现 — `tools/list` JSON-RPC 自动发现 MCP Server 的所有工具
- [x] 15 个 MCP 测试（含 mock subprocess 集成测试）

**P1：子 Agent 系统**
- [x] `SubAgentManager` — asyncio 并发编排，`Semaphore` 控制并发
- [x] `spawn_agent(task, type)` — 孵化子 Agent（code/research/test/generic）
- [x] 资源限制 — 最大并发数（默认 5）、单 Agent 超时（默认 300s）
- [x] 生命周期管理 — `wait()` / `wait_all()` / `kill()` / `cleanup()`
- [x] 结果汇总回主 Agent — `get_agent_status()` 查询输出/错误
- [x] 22 个子 Agent 测试（spawn/kill/timeout/failure/cleanup）

**v0.3.0 总计：214 个测试，ruff 零告警**

### v0.4.0 — 智能化 ✅ 已完成

> **本阶段目标：为框架增加代码智能（LSP）、Web 能力和上下文管理能力。**

**P2：LSP 集成**
- [x] LSP Client 框架 — `LSPClient` 管理语言服务器进程，Content-Length 帧 JSON-RPC
- [x] Python (pyright) / TypeScript (typescript-language-server) / Go (gopls) 支持
- [x] LSP 诊断自动反馈给 LLM — `lsp_diagnostics(file_path)` 工具
- [x] go-to-definition、find-references、hover 工具 — `lsp_definition()`, `lsp_references()`, `lsp_hover()`

**P2：Web 能力**
- [x] `webfetch(url)` — 抓取网页，HTML->Markdown 转换，支持 JSON/纯文本
- [x] `websearch(query)` — DuckDuckGo HTML 搜索，无需 API Key

**P2：上下文管理**
- [x] Auto Compact — `compact_messages()` 接近窗口限制时自动摘要压缩旧消息
- [x] LLM 语义压缩 — `compact_messages_llm()` 用轻量 Agent 生成语义摘要，支持增量合并、独立模型配置、失败自动 fallback
- [x] 大文件分块读取 — `chunk_file()` 带重叠的分块切割
- [x] 智能上下文选择 — `select_relevant_context()` 关键词匹配评分，token 预算控制

### v0.5.0 — 安全与可靠性 ✅ 已完成

> **本阶段目标：为生产环境夯实安全基础——权限、审计、限流、可撤销。**

**P3：安全与可靠性**
- [x] 工具级权限系统 — `PermissionManager` per-tool allow/deny/confirm，内置默认规则，支持用户覆盖
- [x] 文件修改 undo/redo — `FileHistory` 记录 write/edit/patch 快照，undo/redo 栈
- [x] 审计日志 — `AuditLogger` SQLite 持久化，8 种事件类型，query/count/clear
- [x] 速率限制 — `RateLimiter` 滑动窗口算法，per-key 限流
- [x] API 三层中间件 — auth -> rate_limit -> audit，所有非公开端点自动拦截
- [x] 新 API — `GET /audit` 查询审计日志
- [x] 新工具 — `undo_file`, `redo_file`, `list_file_changes`

**TUI 参考实现**
- [x] Textual 全屏终端 UI — `CodyTUI` App，MessageBubble/StreamBubble/StatusLine 组件
- [x] 流式响应 — 异步 `run_stream()` 实时输出
- [x] 会话管理 — 新建/恢复/列出会话，Ctrl+N 快捷键
- [x] 斜杠命令 — `/help`, `/new`, `/sessions`, `/clear`, `/quit`
- [x] CLI 集成 — `cody tui` 命令 + `cody-tui` console_scripts 入口

**v0.5.0 总计：418 个测试，ruff 零告警**

### v1.0.0 — 框架成熟 ✅ 已完成

> **本阶段目标：扩展框架生态——CI/CD 模板、更多内置 Skills，完成核心功能闭环。**

**CI/CD 模板**
- [x] GitHub Actions 模板 — `templates/github-actions/` 目录
  - `ai-code-review.yml` — PR 自动 AI 代码审查
  - `ai-fix-issues.yml` — Issue 标签触发自动修复并开 PR
  - `ai-test-gen.yml` — 自动为变更文件生成测试
- [x] CI/CD Skill — `cicd` 技能文档，覆盖 GitHub Actions / GitLab CI 用法

**更多内置 Skills（5 -> 11，v1.11.0 后移除内置 Skills，改为用户自建）**
- [x] `web` — 网页搜索和抓取（websearch/webfetch 工具使用指南）
- [x] `rust` — Rust/Cargo 项目管理（构建、测试、Clippy、工作空间）
- [x] `go` — Go 项目管理（模块、测试、golangci-lint、交叉编译）
- [x] `java` — Java/Maven/Gradle 项目管理（Spring Boot、JUnit 5、Mockito）
- [x] `cicd` — CI/CD 流水线管理（GitHub Actions、GitLab CI、Cody 集成）
- [x] `testing` — 跨语言测试策略和模式（pytest、Jest、go test、cargo test）

**v1.0.0 总计：418 个 Python 测试，ruff 零告警，3 个 CI/CD 模板**

### v1.0.1 — Agent Skills 开放标准 & 多模型生态 ✅ 已完成

> **本阶段目标：Skill 系统对齐 [Agent Skills 开放标准](https://agentskills.io/)，扩展多模型生态。**

**Skill 格式迁移**
- [x] 11 个 SKILL.md 全部迁移到 YAML frontmatter + Markdown 标准格式
- [x] 必填字段：`name`（<=64 字符，小写+连字符）、`description`（<=1024 字符）
- [x] 可选字段：`license`、`compatibility`、`metadata`、`allowed-tools`
- [x] `name` 必须与目录名一致

**SkillManager 重构**
- [x] YAML frontmatter 解析器（零外部依赖）
- [x] 名称校验（正则匹配、目录名一致性检查）
- [x] `validate_skill()` — Skill 目录校验（缺字段、格式错误、名称不匹配）
- [x] 无 frontmatter 的纯 Markdown 文件不再加载（不向下兼容）

**渐进式加载（Progressive Disclosure）**
- [x] 启动时只解析 frontmatter（~50-100 tokens/skill）
- [x] `skill.instructions` — 按需加载 SKILL.md body（去掉 frontmatter）
- [x] `to_prompt_xml()` — 生成 `<available_skills>` XML 注入 system prompt
- [x] Runner system prompt 自动注入 skills XML

**阿里云百炼 Coding Plan**
- [x] 集成百炼 Coding Plan API（Qwen3.5、GLM-5、Kimi K2.5、MiniMax M2.5 等）
- [x] 支持 OpenAI 兼容协议
- [x] CLI `--coding-plan-key` / `--coding-plan-protocol` 参数
- [x] 环境变量 `CODY_CODING_PLAN_KEY` / `CODY_CODING_PLAN_PROTOCOL`

**v1.0.1 总计：446 个 Python 测试，ruff 零告警**

### v1.1.0 — Thinking Mode & StreamEvent ✅ 已完成

> **本阶段目标：统一流式事件系统，支持 thinking 模式，框架所有接入方式获得完整的 AI 执行过程信息。**

**Thinking Mode**
- [x] `enable_thinking` + `thinking_budget` 配置字段
- [x] CLI `--thinking/--no-thinking` 和 `--thinking-budget` 参数（run/chat/tui）
- [x] HTTP API 请求参数支持 `enable_thinking` 和 `thinking_budget`
- [x] 环境变量 `CODY_ENABLE_THINKING` / `CODY_THINKING_BUDGET`

**CodyResult 架构**
- [x] `CodyResult` 数据模型 — output + thinking + tool_traces + usage
- [x] `ToolTrace` — 记录每次工具调用的 tool_name、args、result
- [x] 核心引擎给出全部信息，上层（CLI/TUI/Web/SDK）选择怎么展示

**StreamEvent 统一流式事件系统**
- [x] 5 种结构化事件类型：`ThinkingEvent`、`TextDeltaEvent`、`ToolCallEvent`、`ToolResultEvent`、`DoneEvent`
- [x] `run_stream()` 基于 pydantic-ai `run_stream_events()` API，实时 yield 结构化事件
- [x] CLI run/chat 从同步 `run_sync()` 改为异步流式 `run_stream()`，打字机效果输出
- [x] TUI 消费 StreamEvent，修复 message history 重建 bug
- [x] HTTP SSE/WebSocket 发送结构化事件（thinking/tool_call/tool_result/text_delta/done）
- [x] `_serialize_stream_event()` 统一 SSE 和 WebSocket 的序列化

**v1.1.0 总计：476 个 Python 测试**

### v1.6.0 — SDK 增强 & 框架优化 ✅ 已完成

> **本阶段目标：完善 Python SDK，优化框架性能，拆分依赖让 SDK 用户轻量安装。**

**增强 SDK（`cody/sdk/`）**
- [x] Builder 模式 — `Cody().workdir(...).model(...).build()` 链式创建客户端
- [x] 事件系统 — `EventManager` 同步/异步事件分发、装饰器注册
- [x] 指标采集 — `MetricsCollector` 记录 token 使用、工具调用、会话统计
- [x] 10 种错误类型 — `CodyError` -> `CodyAuthError` / `CodyModelError` / `CodyToolError` 等
- [x] 4 个示例文件 — basic.py、streaming.py、events_demo.py、tools_demo.py
- [x] 65 个 SDK 测试

**TUI 性能优化**
- [x] 30fps 批量渲染 — StreamBubble buffer + timer flush，替代逐 chunk update
- [x] 滚动节流 — 移除事件循环中的手动 scroll_end，改由 flush 统一处理
- [x] 工具参数截断 — 超过 120 字符的参数值截断显示，防止屏幕溢出
- [x] 工具结果摘要 — ToolResultEvent 显示摘要行而非完整内容
- [x] 消息回收 — 超过 200 个 widget 时自动移除最旧的消息

**CLI 工具参数截断**
- [x] 与 TUI 一致的 120 字符截断策略

**PyPI 依赖分层**
- [x] 核心依赖仅 3 个 — pydantic-ai、pydantic、httpx
- [x] 可选依赖组 — `[cli]`、`[tui]`、`[web]`、`[repl]`、`[all]`、`[dev]`
- [x] 入口模块友好报错 — 缺依赖时提示 `pip install cody-ai[xxx]`
- [x] 移除未使用的 python-dotenv 依赖
- [x] 移除 OAuth 认证模块，统一为 `model_api_key` 方式

**代码审查修复（S1-S5, R1-R10, O2-O8）**
- [x] S1: `run_sync()` 补充上下文压缩调用
- [x] S2: HTML 解析器嵌套 skip 标签改为深度计数器
- [x] S3: WebSocket 端点增加认证检查
- [x] S4: CI 重写（Python 3.9-3.13 矩阵、Web 测试覆盖），删除 pylint.yml
- [x] S5: 可扩展 `blocked_commands` + 管道命令白名单逐段检查
- [x] R1: CLI/TUI 共享工具库 `cody/shared.py`
- [x] R3: `ToolContext` 统一工具直接调用上下文
- [x] R7: Config 缓存 60s TTL
- [x] R9: 新增 21 个 Web 路由测试

**v1.6.0 总计：673+ 个测试（588 core/sdk + 85 web），ruff 零告警**

### v1.9.0 — MCP HTTP 传输 & SDK MCP 增强 ✅ 已完成

> **本阶段目标：MCP 支持 HTTP 传输，SDK 提供完整的 MCP 管理 API。**

**MCP HTTP 传输**
- [x] `MCPClient` 新增 HTTP transport — `httpx.AsyncClient` JSON-RPC over HTTP POST
- [x] `MCPServerConfig` 新增 `transport`、`url`、`headers` 字段
- [x] stdio 和 HTTP 服务器可混合运行，统一 `running_servers` / `list_tools()` / `call_tool()`
- [x] 飞书/Lark MCP 等远程端点支持

**SDK MCP 增强**
- [x] Builder API — `.mcp_stdio_server()` / `.mcp_http_server()` 链式配置
- [x] `auto_start_mcp` 参数 — 设为 `True` 时首次 `run()` 自动启动（默认 `False`）
- [x] `add_mcp_server()` — 运行时动态添加并立即启动 MCP 服务器
- [x] `mcp_list_tools()` / `mcp_call()` — SDK 直接调用 MCP 工具
- [x] 动态系统提示 — `@agent.system_prompt` 延迟注入 MCP 工具描述
- [x] 修复 SDK MCP 配置丢失问题 — `_get_config()` 正确传递 MCP 服务器到 core

**测试**
- [x] 7 个新 HTTP transport 测试（test_mcp.py 共 21 个）

---

**最后更新：** 2026-03-20
