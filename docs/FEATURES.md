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

## 路线图

### v0.1.0（MVP）
- [x] 基础 Agent 框架
- [x] 核心工具（file/exec）
- [x] CLI 基本功能
- [x] 项目配置支持

### v0.2.0
- [ ] Skill 系统
- [ ] RPC Server
- [ ] OAuth 认证
- [ ] 更多内置工具

### v0.3.0
- [ ] MCP 集成
- [ ] 子 Agent 系统
- [ ] Web UI（可选）
- [ ] 插件市场

### v1.0.0
- [ ] 生产就绪
- [ ] 完整文档
- [ ] 性能优化
- [ ] 安全加固

---

## 竞品对比

| 功能 | Cody | Claude Code | Cursor | Aider |
|------|------|-------------|--------|-------|
| CLI 模式 | ✅ | ✅ | ❌ | ✅ |
| RPC 调用 | ✅ | ❌ | ❌ | ❌ |
| Skill 系统 | ✅ | ❌ | ❌ | ❌ |
| MCP 支持 | ✅ | ✅ | ❌ | ❌ |
| 多模型 | ✅ | ❌ | ✅ | ✅ |
| 子 Agent | ✅ | ❌ | ❌ | ❌ |
| 开源 | ✅ | ❌ | ❌ | ✅ |

---

**最后更新：** 2026-01-28
