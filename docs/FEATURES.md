# Cody - Product Features

## 概述

Cody 是一个 AI 编程助手，类似 Claude Code，但支持 RPC 调用、动态 Skill 系统和 MCP 集成。

## 核心定位

> **Cody 的核心是 AI 编程引擎（core），CLI 和 Server 都只是引擎的壳子。**
> 引擎做厚，壳子做薄。Server/SDK 是我们的差异化交付方式——让别人把 AI 编程能力嵌入到自己的系统中。

**目标用户：**
- **AI 系统/平台** — 通过 RPC Server / SDK 嵌入 Cody 引擎（**差异化优势**）
- **自动化系统** — 集成到 CI/CD、代码审查、自动修复流程
- **程序员** — 通过 CLI 直接使用（保证可用，也是最好的 dogfooding 方式）

**核心价值：**
- 高质量的 AI 编程引擎（工具准确、Agent 可靠）
- 多种接入方式（Server/SDK/CLI 共享同一引擎）
- 可扩展的 Skill 系统
- 子 Agent 编排（任务分解、并行执行）

---

## 功能清单

### 1. 核心 AI 能力

**基于 Pydantic AI：**
- 多模型支持（Anthropic、OpenAI、Google、DeepSeek 等）
- 结构化输出
- 工具调用（Function Calling）
- 流式响应
- 会话管理

**认证方式：**
- OAuth 2.0（推荐）
- API Key（备选）
- 多账号支持

### 2. 内置工具集

**文件操作：**
- `read_file(path)` - 读取文件
- `write_file(path, content)` - 写入文件
- `edit_file(path, old_text, new_text)` - 精确编辑
- `list_directory(path)` - 列出目录
- `search_files(pattern, path)` - 搜索文件

**命令执行：**
- `exec_command(command)` - 执行 Shell 命令
- `exec_background(command)` - 后台执行
- `kill_process(pid)` - 终止进程

**Git 操作：**
- `git_status()` - 查看状态
- `git_diff()` - 查看差异
- `git_commit(message)` - 提交
- `git_push()` - 推送

**Skill 元工具：**
- `list_skills()` - 列出可用 Skills
- `read_skill(name)` - 读取 Skill 文档
- AI 根据 SKILL.md 学习使用方式

### 3. Skill 系统

**动态加载：**
```
.cody/skills/          # 项目 Skills（最高优先级）
~/.cody/skills/        # 全局 Skills
{安装目录}/skills/     # 内置 Skills
```

**Skill 结构：**
```
skills/github/
├── SKILL.md          # AI 读取的文档
├── examples/         # 示例（可选）
└── scripts/          # 辅助脚本（可选）
```

**内置 Skills：**
- `git` - Git 操作
- `github` - GitHub CLI 集成
- `docker` - Docker 操作
- `npm` - Node.js 项目管理
- `python` - Python 项目管理
- `web` - 网页搜索和抓取

**Skill 管理命令：**
```bash
cody skills list                  # 列出可用 Skills
cody skills enable <name>         # 启用 Skill
cody skills disable <name>        # 禁用 Skill
cody skills create <name>         # 创建新 Skill
```

### 4. MCP 集成

**支持方式：**
- 作为 MCP Client 连接外部 MCP Servers
- 支持本地和远程 Server
- 配置化管理

**配置示例：**
```json
{
  "mcp": {
    "servers": [
      {
        "name": "github",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {
          "GITHUB_TOKEN": "..."
        }
      }
    ]
  }
}
```

**常用 MCP Servers：**
- GitHub Server
- Database Server
- Filesystem Server
- Web Search Server

### 5. 子 Agent 系统

**功能：**
- 主 Agent 可以孵化子 Agent 处理特定任务
- 子 Agent 独立运行，完成后返回结果
- 支持不同类型的子 Agent（编码、研究、测试等）

**工具：**
- `spawn_agent(task, type)` - 孵化子 Agent
- `get_agent_status(agent_id)` - 查询子 Agent 状态
- `kill_agent(agent_id)` - 终止子 Agent

**使用场景：**
- 复杂任务分解
- 并行处理多个子任务
- 专门化处理（编码/研究/测试分离）

### 6. 双模式运行

#### CLI 模式

**基本使用：**
```bash
# 初始化项目
cody init

# 直接对话
cody "创建一个 FastAPI 项目"

# 交互模式
cody chat

# 指定模型
cody --model opus "复杂任务"

# 继续上次对话
cody --continue "继续刚才的任务"
```

**配置管理：**
```bash
cody config get                   # 查看配置
cody config set key value         # 设置配置
cody auth login                   # OAuth 登录
cody auth status                  # 查看认证状态
```

#### RPC Server 模式

**启动服务：**
```bash
# 默认端口 8000
cody-server

# 指定端口
cody-server --port 9000

# 指定主机
cody-server --host 0.0.0.0
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
  "prompt": "创建项目",
  "stream": true
}

// SSE 流式响应
data: {"type": "text", "content": "正在"}
data: {"type": "text", "content": "创建"}
data: {"type": "tool", "tool": "write_file", "args": {...}}
data: {"type": "done", "output": "完成"}
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
  "version": "0.1.0"
}
```

### 7. 项目配置

**`.cody/config.json`（项目级）：**
```json
{
  "model": "anthropic:claude-sonnet-4-0",
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
  "auth": {
    "type": "oauth",
    "token": "...",
    "refresh_token": "...",
    "expires_at": "2026-02-01T00:00:00Z"
  },
  "default_model": "anthropic:claude-sonnet-4-0",
  "skills": {
    "enabled": ["git"]
  }
}
```

### 8. 安全特性

**命令执行限制：**
- 白名单机制
- 危险命令拦截（rm -rf、dd 等）
- 需要确认的操作

**权限管理：**
- 文件访问限制（在项目目录内）
- 网络访问控制
- 子 Agent 资源限制

**审计日志：**
- 记录所有命令执行
- 记录文件修改
- 记录 API 调用

---

## 技术架构

**核心技术栈：**
- Python 3.9+
- Pydantic AI
- FastAPI（RPC Server）
- Click（CLI）
- Rich（终端 UI）

**模型支持：**
- Anthropic Claude（推荐）
- OpenAI GPT
- Google Gemini
- DeepSeek
- 其他兼容 OpenAI API 的模型

---

## 使用场景

### 1. 独立使用（程序员）
```bash
cd ~/myproject
cody init
cody "帮我重构 auth.py，提取通用逻辑到 utils.py"
```

### 2. 集成到 Clawdbot
```javascript
// Clawdbot 调用 Cody
const response = await fetch('http://localhost:8000/run', {
  method: 'POST',
  body: JSON.stringify({
    prompt: '创建一个 API 路由',
    workdir: process.cwd()
  })
});
```

### 3. CI/CD 集成
```yaml
# .github/workflows/ai-review.yml
- name: AI Code Review
  run: |
    cody "检查代码质量并生成报告" > review.md
```

### 4. 多项目管理
```bash
# 项目 A 有自己的 skills
cd ~/project-a
cody "使用项目 A 的配置"

# 项目 B 有不同的 skills
cd ~/project-b
cody "使用项目 B 的配置"
```

---

## 竞品分析

### 主要竞品

| 功能 | Cody | OpenCode/Crush | Claude Code | Cursor | Aider |
|------|------|---------------|-------------|--------|-------|
| CLI 模式 | ✅ | ✅ | ✅ | ❌ | ✅ |
| 交互式 TUI | ❌ | ✅（Bubble Tea） | ✅ | N/A | ❌ |
| **RPC Server** | **✅ 核心优势** | ❌ | ❌ | ❌ | ❌ |
| Skill 系统 | ✅ | ✅ | ❌ | ❌ | ❌ |
| MCP 支持 | ✅ | ✅ | ✅ | ❌ | ❌ |
| LSP 集成 | ✅ | ✅（30+ 语言） | ❌ | ✅（内置） | ❌ |
| 多模型 | ✅ | ✅（75+ 提供商） | ❌ | ✅ | ✅ |
| 子 Agent | ✅ | ❌ | ✅ | ❌ | ❌ |
| 会话管理 | ✅（SQLite） | ✅（SQLite） | ✅ | ✅ | ✅ |
| Web 搜索/抓取 | ✅ | ✅ | ✅ | ✅ | ❌ |
| Undo/Redo | ✅ | ✅ | ❌ | ✅ | ✅ |
| GitHub 集成 | ❌ | ✅（PR/Issue 触发）| ✅ | ✅ | ✅ |
| 开源 | ✅（MIT） | ✅（MIT） | ❌ | ❌ | ✅ |

### OpenCode/Crush 重点能力分析

**OpenCode**（SST 维护，MIT 开源，10.9K Stars）和 **Crush**（Charm 团队维护，原作者在此，Charm License 私有协议）是同源分裂的两个项目。它们的核心优势：

1. **LSP 集成** — 内置 30+ 语言服务器，AI 不仅靠文本推理，还能获取编译器级别的类型信息、诊断错误、引用关系
2. **精美 TUI** — 基于 Bubble Tea 的终端界面，Build/Plan 双模式，Vim 风格编辑器
3. **会话系统** — SQLite 持久化，多会话切换，Auto Compact 自动摘要压缩上下文
4. **丰富的内置工具** — bash, read, write, edit, grep, glob, patch, webfetch, websearch, todowrite, question 等
5. **权限系统** — 工具级别的权限控制

### Cody 的差异化优势

1. **RPC Server 模式** — OpenCode/Crush 没有，Cody 可作为"可嵌入的 AI 编码引擎"
2. **Python 生态** — AI/ML 生态更丰富（Pydantic AI、FastAPI），开发迭代更快
3. **动态 Skill 系统** — 三层加载、项目级定制，比 OpenCode 的 skill 系统更完善
4. **子 Agent 架构** — Python asyncio 并发 Agent 编排，code/research/test 专业化子 Agent

---

## 战略定位

**核心策略：引擎做厚，壳子做薄。**

```
CLI (薄壳) ──→ Core Engine (厚) ←── Server/SDK (薄壳)
```

CLI 和 Server 都只是 core 的接入层。我们的精力分配：
- **Core 引擎**（最高优先级） — 工具质量、Agent 能力、准确度，这是一切的基础
- **Server + SDK**（差异化重点） — 可嵌入的交付方式，别人没有的东西
- **子 Agent + MCP** — Python 生态天然适合 AI Agent 编排
- **CLI** — 保证可用，不花大力气打磨 TUI（不跟 Charm/Anthropic 卷这个方向）

---

## 路线图

### v0.1.0（MVP）✅ 已完成
- [x] 基础 Agent 框架（Pydantic AI）
- [x] 核心工具（read_file, write_file, edit_file, list_directory, exec_command）
- [x] CLI 基本功能（run, init, skills, config）
- [x] 项目配置支持（全局/项目级 config.json）
- [x] Skill 系统基础（三层加载、SKILL.md、enable/disable）
- [x] RPC Server 骨架（FastAPI, /run, /run/stream, /tool, /skills, /health）

### v0.2.0（工具与会话）✅ 已完成
- [x] 搜索工具（grep, glob, search_files）— 正则搜索、模式匹配、模糊文件名搜索
- [x] patch 工具 — 应用 unified diff 补丁
- [x] 搜索准确度对齐 ripgrep — 二进制文件检测、.gitignore 支持、默认忽略目录
- [x] 路径遍历安全修复 — resolve() 防止 symlink 逃逸
- [x] SQLite 会话持久化 — 对话历史存储、多会话管理
- [x] CLI 交互模式 — `cody chat`、`--continue`、`--session`
- [x] 81 个单元测试，ruff 零告警（现 144 个）

### v0.3.0 — 引擎化 ✅ 已完成

> **本阶段目标：把 Cody 从一个 CLI 工具变成一个可嵌入的 AI 编程引擎。**
> Server 和 SDK 是重点，CLI 功能冻结。

**P0：Server API 完善**
- [x] Session API — `POST /sessions`, `GET /sessions`, `GET /sessions/:id`, `DELETE /sessions/:id`
- [x] 带会话的对话 — `POST /run` 支持 `session_id` 参数，自动持久化对话历史
- [x] SSE 结构化 JSON 事件 — `{type: text/done/error}`
- [x] Server 完整测试 — 32+ 个端点测试
- [x] Runner + Session 打通 — `run_with_session` / `run_stream_with_session`
- [x] 结构化错误响应 — 统一 `ErrorCode` 枚举、`CodyAPIError`、`{"error": {"code", "message", "details"}}` 格式
- [x] WebSocket 双向通信 — `WS /ws` 端点，支持 run/cancel/ping，实时流式推送
- [x] Sub-Agent API — `POST /agent/spawn`, `GET /agent/:id`, `DELETE /agent/:id`

**P0：Python SDK**
- [x] `CodyClient` / `AsyncCodyClient` — 同步 + 异步双客户端
- [x] 核心方法 — `run()`, `stream()`, `tool()`, `health()`
- [x] 会话管理 — `create_session()`, `list_sessions()`, `get_session()`, `delete_session()`
- [x] 错误处理 — `CodyError`, `CodyConnectionError`, `CodyNotFoundError`, `CodyTimeoutError`
- [x] 结构化错误解析 — 自动解析 `{"error": {"code", "message"}}` 格式，兼容旧 `detail` 格式
- [x] 自动重连 — `max_retries` 参数（默认 3），指数退避（0.5s → 1s → 2s → 4s → 8s 上限）
- [x] 19+ 个 SDK 测试 + 18 个 retry 测试

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

> **本阶段目标：让 Cody 拥有代码智能（LSP）、Web 能力和上下文管理能力。**

**P2：LSP 集成**
- [x] LSP Client 框架 — `LSPClient` 管理语言服务器进程，Content-Length 帧 JSON-RPC
- [x] Python (pyright) / TypeScript (typescript-language-server) / Go (gopls) 支持
- [x] LSP 诊断自动反馈给 LLM — `lsp_diagnostics(file_path)` 工具
- [x] go-to-definition、find-references、hover 工具 — `lsp_definition()`, `lsp_references()`, `lsp_hover()`

**P2：Web 能力**
- [x] `webfetch(url)` — 抓取网页，HTML→Markdown 转换，支持 JSON/纯文本
- [x] `websearch(query)` — DuckDuckGo HTML 搜索，无需 API Key

**P2：上下文管理**
- [x] Auto Compact — `compact_messages()` 接近窗口限制时自动摘要压缩旧消息
- [x] 大文件分块读取 — `chunk_file()` 带重叠的分块切割
- [x] 智能上下文选择 — `select_relevant_context()` 关键词匹配评分，token 预算控制

### v0.5.0 — 安全与可靠性 ✅ 已完成

> **本阶段目标：为生产环境夯实安全基础——认证、权限、审计、限流、可撤销。**

**P3：安全与可靠性**
- [x] OAuth 2.0 认证 — `AuthManager` 支持 API Key 验证 + HMAC-SHA256 签名 token 签发/校验/刷新
- [x] 工具级权限系统 — `PermissionManager` per-tool allow/deny/confirm，内置默认规则，支持用户覆盖
- [x] 文件修改 undo/redo — `FileHistory` 记录 write/edit/patch 快照，undo/redo 栈
- [x] 审计日志 — `AuditLogger` SQLite 持久化，8 种事件类型，query/count/clear
- [x] 速率限制 — `RateLimiter` 滑动窗口算法，per-key 限流
- [x] Server 三层中间件 — auth → rate_limit → audit，所有非公开端点自动拦截
- [x] 新 API — `GET /audit` 查询审计日志
- [x] 新工具 — `undo_file`, `redo_file`, `list_file_changes`

**v0.5.0 总计：406 个测试，ruff 零告警**

### v1.0.0 — 生产就绪

**P3：生态**
- [ ] TypeScript SDK
- [ ] GitHub 集成（PR/Issue 触发）
- [ ] CI/CD 模板
- [ ] 更多内置 Skills
- [ ] Docker 镜像

---

**最后更新：** 2026-02-13
