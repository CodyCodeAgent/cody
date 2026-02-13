# Cody - Product Features

## 概述

Cody 是一个 AI 编程助手，类似 Claude Code，但支持 RPC 调用、动态 Skill 系统和 MCP 集成。

## 核心定位

**目标用户：**
- 程序员（直接使用 CLI）
- AI Agent（通过 RPC 调用 Cody）
- 自动化系统（集成到 CI/CD）

**核心价值：**
- AI 驱动的代码生成和编辑
- 可扩展的工具和技能系统
- 支持多种调用方式（CLI + RPC）
- 项目级配置和技能管理

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
| RPC 调用 | ✅ | ❌ | ❌ | ❌ | ❌ |
| Skill 系统 | ✅ | ✅ | ❌ | ❌ | ❌ |
| MCP 支持 | 🔲 仅数据结构 | ✅ | ✅ | ❌ | ❌ |
| LSP 集成 | ❌ | ✅（30+ 语言） | ❌ | ✅（内置） | ❌ |
| 多模型 | ✅ | ✅（75+ 提供商） | ❌ | ✅ | ✅ |
| 子 Agent | ❌ | ❌ | ✅ | ❌ | ❌ |
| 会话管理 | ❌ | ✅（SQLite） | ✅ | ✅ | ✅ |
| Web 搜索/抓取 | ❌ | ✅ | ✅ | ✅ | ❌ |
| Undo/Redo | ❌ | ✅ | ❌ | ✅ | ✅ |
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
4. **子 Agent 架构**（规划中） — Python asyncio 天然适合并发 Agent 编排

---

## 战略定位

**核心策略：不在 TUI 颜值上和 Charm 团队卷，重点放在 AI 能力深度和可嵌入性。**

Cody 的目标是成为：
- 对**程序员**：一个能力强大的终端 AI 编程助手（CLI + 交互模式）
- 对**其他 AI 系统**：一个可嵌入的 AI 编码引擎（RPC Server）
- 对**自动化系统**：一个可集成到 CI/CD 的编码工具

---

## 路线图

### v0.1.0（MVP）✅ 已完成
- [x] 基础 Agent 框架（Pydantic AI）
- [x] 核心工具（read_file, write_file, edit_file, list_directory, exec_command）
- [x] CLI 基本功能（run, init, skills, config）
- [x] 项目配置支持（全局/项目级 config.json）
- [x] Skill 系统基础（三层加载、SKILL.md、enable/disable）
- [x] RPC Server 基础（FastAPI, /run, /run/stream, /tool, /skills, /health）

### v0.2.0 — 让 Cody "能用起来"

**P0：交互式模式（核心）**
- [ ] REPL/Chat 交互模式（`cody chat`），支持持续对话
- [ ] 基于 prompt_toolkit 或 Textual 的终端交互界面
- [ ] 流式输出显示（打字机效果）
- [ ] 输入历史、自动补全

**P0：补齐基础工具**
- [ ] `grep(pattern, path)` — 正则搜索文件内容
- [ ] `glob(pattern)` — 按模式匹配查找文件
- [ ] `patch(path, diff)` — 应用 diff 补丁修改文件
- [ ] `search_files(query, path)` — 模糊搜索文件名

**P0：会话与上下文管理**
- [ ] SQLite 持久化对话历史
- [ ] `--continue` / `--session <id>` 继续/切换会话
- [ ] Auto Compact — 接近上下文窗口限制时自动摘要压缩
- [ ] 会话列表查看和管理

### v0.3.0 — 让 Cody "好用"

**P1：LSP 集成**
- [ ] LSP Client 基础框架（基于 pygls 或自建）
- [ ] Python 语言服务器支持（pyright）
- [ ] TypeScript 语言服务器支持（typescript-language-server）
- [ ] Go 语言服务器支持（gopls）
- [ ] LSP 诊断自动反馈给 LLM（AI 改完代码后立刻知道有没有错）
- [ ] AI 可调用 go-to-definition、find-references
- [ ] LSP 服务器自动检测和按需启动

**P1：MCP 集成（落地实现）**
- [ ] MCP Client 实现（基于 mcp Python SDK）
- [ ] 从配置文件加载 MCP Server
- [ ] MCP Server 生命周期管理（启动/停止/重连）
- [ ] MCP 工具自动注册到 Agent
- [ ] 常用 MCP Server 预置配置（GitHub、数据库、文件系统）

**P1：Web 能力**
- [ ] `webfetch(url)` — 抓取网页内容，转为 Markdown
- [ ] `websearch(query)` — 搜索引擎集成（Exa / Tavily / SerpAPI）
- [ ] 搜索结果摘要和提取

**P1：用户交互增强**
- [ ] `question()` 工具 — AI 在执行过程中向用户提问
- [ ] 工具执行前确认提示（可配置）
- [ ] `todowrite` / `todoread` — AI 管理任务列表

### v0.4.0 — 让 Cody "有特色"

**P2：子 Agent 系统**
- [ ] SubAgentManager 实现
- [ ] `spawn_agent(task, type)` — 孵化子 Agent
- [ ] `get_agent_status(agent_id)` — 查询状态
- [ ] `kill_agent(agent_id)` — 终止子 Agent
- [ ] 子 Agent 类型：code（编码）、research（研究）、test（测试）
- [ ] asyncio 并发运行，资源限制（最大数量、超时）
- [ ] 结果汇总回主 Agent

**P2：RPC Server 增强**
- [ ] WebSocket 实时双向通信
- [ ] 会话管理 API（创建/恢复/列表）
- [ ] 工具级权限 API
- [ ] 流式工具调用事件推送
- [ ] SDK 封装（Python client / TypeScript client）
- [ ] 完善 API 文档（OpenAPI / Swagger）

**P2：Undo/Redo 与安全**
- [ ] 文件修改记录与回滚（undo/redo）
- [ ] 工具级权限系统（每次执行可配置是否需要确认）
- [ ] 审计日志（记录所有命令执行、文件修改、API 调用）
- [ ] 敏感信息检测（防止 .env、密钥等被意外操作）

### v1.0.0 — 让 Cody "可信赖"

**P3：生产就绪**
- [ ] 完整测试覆盖（单元测试 + 集成测试 + RPC 测试）
- [ ] 性能优化（Skill 缓存、模型响应缓存、并发工具调用）
- [ ] 错误处理和恢复机制
- [ ] 完整用户文档和开发者文档

**P3：生态扩展**
- [ ] GitHub 集成（PR/Issue 评论触发 Cody）
- [ ] CI/CD 集成指南和模板
- [ ] 自定义命令系统
- [ ] 更多内置 Skills（github, docker, npm, python, web）
- [ ] OAuth 2.0 认证流程
- [ ] Desktop App / IDE 插件（可选）

---

**最后更新：** 2026-02-13
