# Cody - Product Features

## 概述

Cody 是一个 AI 编程助手，类似 Claude Code，但支持 RPC 调用、动态 Skill 系统和 MCP 集成。

## 核心定位

> **Cody 的核心是 AI 编程引擎（core），CLI、Web 和 Server 都只是引擎的壳子。**
> 引擎做厚，壳子做薄。Server/SDK 是我们的差异化交付方式——让别人把 AI 编程能力嵌入到自己的系统中。

**目标用户：**
- **AI 系统/平台** — 通过 RPC Server / SDK 嵌入 Cody 引擎（**差异化优势**）
- **自动化系统** — 集成到 CI/CD、代码审查、自动修复流程
- **程序员** — 通过 CLI/TUI 直接使用（保证可用，也是最好的 dogfooding 方式）

**核心价值：**
- 高质量的 AI 编程引擎（工具准确、Agent 可靠）
- 多种接入方式（Server/SDK/CLI/TUI/Web 共享同一引擎）
- 可扩展的 Skill 系统
- 子 Agent 编排（任务分解、并行执行）

---

## 功能清单

### 1. 核心 AI 能力

**基于 Pydantic AI：**
- 多模型支持（Anthropic、OpenAI、Google、DeepSeek 等）
- 自定义 OpenAI 兼容 API 支持（智谱 GLM、阿里通义千问/DashScope 等）
- 结构化输出
- 工具调用（Function Calling）
- 流式响应（结构化 StreamEvent：thinking / tool_call / tool_result / text_delta / done）
- 会话管理
- Thinking 模式（`--thinking` 开启，`--thinking-budget` 控制 token 预算）

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

**搜索工具：**
- `grep(pattern, path, include)` - 正则搜索文件内容
- `glob(pattern, path)` - 模式匹配查找文件
- `search_files(query, path)` - 模糊文件名搜索
- `patch(path, diff)` - 应用 unified diff 补丁

**命令执行：**
- `exec_command(command)` - 执行 Shell 命令（支持白名单和危险命令检测）

**工具错误自动重试：**
- 工具执行失败（如 `edit_file` 找不到目标文本）时，错误信息自动返回给 AI 模型
- AI 可以根据错误信息修正参数后重试（最多 2 次重试）
- 基于 pydantic-ai 的 `ModelRetry` 机制，不会打断整个对话流

**任务管理：**
- `todo_write(todos)` - 创建/更新任务清单
- `todo_read()` - 读取当前任务清单

**用户交互：**
- `question(text, options)` - 向用户提结构化选择题

**Skill 元工具：**
- `list_skills()` — 列出可用 Skills（只返回元数据，渐进式加载）
- `read_skill(name)` — 加载 Skill 完整指令（按需激活）
- System prompt 自动注入 `<available_skills>` XML，AI 按上下文匹配

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

**三层优先级加载：**
```
.cody/skills/          # 项目 Skills（最高优先级）
~/.cody/skills/        # 全局 Skills
{安装目录}/skills/     # 内置 Skills
```

**渐进式加载（Progressive Disclosure）：**
1. 启动时 — 只解析 YAML frontmatter（name + description）
2. 激活时 — 加载完整 SKILL.md body
3. 按需 — 读取 scripts/、references/、assets/

**内置 Skills（11 个）：**
- `git` — Git 版本控制操作
- `github` — GitHub CLI 集成
- `docker` — Docker 容器管理
- `npm` — Node.js/npm 项目管理
- `python` — Python 项目管理
- `web` — 网页搜索和抓取
- `rust` — Rust/Cargo 项目管理
- `go` — Go 项目管理
- `java` — Java/Maven/Gradle 项目管理
- `cicd` — CI/CD 流水线管理
- `testing` — 跨语言测试策略

**Skill 管理命令：**
```bash
cody skills list                  # 列出可用 Skills
cody skills enable <name>         # 启用 Skill
cody skills disable <name>        # 禁用 Skill
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

### 6. 四模式运行 + SDK

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
cody config show                  # 查看配置
cody config set model <value>     # 设置模型
```

#### TUI 模式

**全屏交互终端（基于 Textual）：**
```bash
# 启动 TUI
cody tui

# 继续上次会话
cody tui --continue

# 恢复指定会话
cody tui --session <id>

# 直接启动
cody-tui
```

**功能：**
- 流式响应实时显示
- 多会话管理（新建/恢复/列出/切换）
- 斜杠命令（/help, /new, /sessions, /clear, /quit）
- 键盘快捷键（Ctrl+N 新会话, Ctrl+C 取消/退出, Ctrl+Q 退出）
- 状态栏显示 Session、Model、目录、消息数

#### Web 前端

独立 Web 应用，遵循"引擎做厚，壳子做薄"理念。

**架构：** `React (Vite:5173) → Web Backend (FastAPI:8000, web.db) → Core Engine`

**功能：**
- 项目管理 — 创建/编辑/删除项目（名称、描述、工作目录）
- 项目向导 — 目录浏览器选择 workdir，自动初始化 `.cody/`
- 实时对话 — WebSocket 流式消息显示，通过 SDK 代理到核心服务
- 项目侧边栏 — 快速切换/删除项目
- 深色主题 UI

**Web Backend（`web/backend/`）：**
- 统一 FastAPI 应用（端口 8000），同时提供 RPC API 和 Web 功能
- 自有 SQLite 数据库（`~/.cody/web.db`）管理项目数据
- 直接调用核心引擎（in-process）
- WebSocket `/ws/chat/{project_id}` 代理聊天

**开发：**
```bash
# 启动 Web 后端
PYTHONPATH=. python -m web.backend

# 启动前端开发服务器
cd web && npm install && npm run dev
```

**生产构建：**
```bash
cd web && npm run build
# dist/ 由 Web Backend 自动托管
```

#### Server 模式

**启动服务：**
```bash
# 生产模式（托管 dist/ 静态文件）
cody-web

# 开发模式（同时启动 Vite dev server）
cody-web --dev

# 指定端口
cody-web --port 9000

# 指定主机
cody-web --host 0.0.0.0
```

Server 由 `web/backend/` 统一提供（单一 FastAPI 应用，端口 8000），同时包含 RPC API 和 Web 功能。

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
  "version": "1.3.0"
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

**模型认证方式（优先级从高到低）：**

| 方式 | 配置 | 说明 |
|------|------|------|
| OpenAI 兼容 API | `model_base_url` + `model_api_key` | 智谱 GLM、阿里 DashScope 等 |
| Claude OAuth | `claude_oauth_token` 或 `CLAUDE_OAUTH_TOKEN` 环境变量 | `claude login` 获取的 OAuth token |
| Anthropic API Key | `ANTHROPIC_API_KEY` 环境变量 | 默认方式 |

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
- FastAPI（Web Backend + RPC API）
- Click（CLI）
- Textual（TUI）
- Rich（终端渲染）

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

### 5. 多项目管理
```bash
# 项目 A 有自己的 skills
cd ~/project-a
cody "使用项目 A 的配置"

# 项目 B 有不同的 skills
cd ~/project-b
cody "使用项目 B 的配置"
```

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

**TUI 交互终端**
- [x] Textual 全屏终端 UI — `CodyTUI` App，MessageBubble/StreamBubble/StatusLine 组件
- [x] 流式响应 — 异步 `run_stream()` 实时输出
- [x] 会话管理 — 新建/恢复/列出会话，Ctrl+N 快捷键
- [x] 斜杠命令 — `/help`, `/new`, `/sessions`, `/clear`, `/quit`
- [x] CLI 集成 — `cody tui` 命令 + `cody-tui` console_scripts 入口

**v0.5.0 总计：418 个测试，ruff 零告警**

### v1.0.0 — 生产就绪 ✅ 已完成

> **本阶段目标：扩展生态——CI/CD 模板、更多内置 Skills，完成核心功能闭环。**

**CI/CD 模板**
- [x] GitHub Actions 模板 — `templates/github-actions/` 目录
  - `ai-code-review.yml` — PR 自动 AI 代码审查
  - `ai-fix-issues.yml` — Issue 标签触发自动修复并开 PR
  - `ai-test-gen.yml` — 自动为变更文件生成测试
- [x] CI/CD Skill — `cicd` 技能文档，覆盖 GitHub Actions / GitLab CI 用法

**更多内置 Skills（5 → 11）**
- [x] `web` — 网页搜索和抓取（websearch/webfetch 工具使用指南）
- [x] `rust` — Rust/Cargo 项目管理（构建、测试、Clippy、工作空间）
- [x] `go` — Go 项目管理（模块、测试、golangci-lint、交叉编译）
- [x] `java` — Java/Maven/Gradle 项目管理（Spring Boot、JUnit 5、Mockito）
- [x] `cicd` — CI/CD 流水线管理（GitHub Actions、GitLab CI、Cody 集成）
- [x] `testing` — 跨语言测试策略和模式（pytest、Jest、go test、cargo test）

**v1.0.0 总计：418 个 Python 测试，ruff 零告警，11 个内置 Skills，3 个 CI/CD 模板**

### v1.0.1 — Agent Skills 开放标准 & 阿里云百炼 ✅ 已完成

> **本阶段目标：Skill 系统对齐 [Agent Skills 开放标准](https://agentskills.io/)，集成阿里云百炼 Coding Plan。**

**Skill 格式迁移**
- [x] 11 个 SKILL.md 全部迁移到 YAML frontmatter + Markdown 标准格式
- [x] 必填字段：`name`（≤64 字符，小写+连字符）、`description`（≤1024 字符）
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
- [x] 支持 OpenAI 和 Anthropic 两种协议
- [x] CLI `--coding-plan-key` / `--coding-plan-protocol` 参数
- [x] 环境变量 `CODY_CODING_PLAN_KEY` / `CODY_CODING_PLAN_PROTOCOL`
- [x] Claude OAuth token 认证支持

**v1.0.1 总计：446 个 Python 测试，ruff 零告警**

### v1.1.0 — Thinking Mode & StreamEvent ✅ 已完成

> **本阶段目标：统一流式事件系统，支持 thinking 模式，所有端获得完整的 AI 执行过程信息。**

**Thinking Mode**
- [x] `enable_thinking` + `thinking_budget` 配置字段
- [x] CLI `--thinking/--no-thinking` 和 `--thinking-budget` 参数（run/chat/tui）
- [x] Server 请求参数支持 `enable_thinking` 和 `thinking_budget`
- [x] 环境变量 `CODY_ENABLE_THINKING` / `CODY_THINKING_BUDGET`

**CodyResult 架构**
- [x] `CodyResult` 数据模型 — output + thinking + tool_traces + usage
- [x] `ToolTrace` — 记录每次工具调用的 tool_name、args、result
- [x] 内核给出全部信息，上层（CLI/TUI/Server）选择怎么展示

**StreamEvent 统一流式事件系统**
- [x] 5 种结构化事件类型：`ThinkingEvent`、`TextDeltaEvent`、`ToolCallEvent`、`ToolResultEvent`、`DoneEvent`
- [x] `run_stream()` 基于 pydantic-ai `run_stream_events()` API，实时 yield 结构化事件
- [x] CLI run/chat 从同步 `run_sync()` 改为异步流式 `run_stream()`，打字机效果输出
- [x] TUI 消费 StreamEvent，修复 message history 重建 bug
- [x] Server SSE/WebSocket 发送结构化事件（thinking/tool_call/tool_result/text_delta/done）
- [x] `_serialize_stream_event()` 统一 SSE 和 WebSocket 的序列化

**v1.1.0 总计：476 个 Python 测试**

---

**最后更新：** 2026-02-28
