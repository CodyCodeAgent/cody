# Cody - CLI 使用文档

命令行界面 (CLI) 是 Cody 最常用的交互方式，支持单次任务执行、交互式对话、会话管理等多种模式。

---

## 快速开始

### 安装

```bash
# 从源码安装
git clone https://github.com/SUT-GC/cody.git
cd cody
pip install -e .

# 验证安装
cody --version
```

### 配置 API Key

```bash
# Anthropic (默认)
export ANTHROPIC_API_KEY='sk-ant-...'

# 或使用其他模型提供商
export CODY_MODEL='glm-4'
export CODY_MODEL_BASE_URL='https://open.bigmodel.cn/api/paas/v4/'
export CODY_MODEL_API_KEY='sk-...'

# 阿里云百炼 Coding Plan
export CODY_CODING_PLAN_KEY='sk-sp-...'
```

### 初始化项目

```bash
# 在当前目录创建 .cody/ 配置目录，并生成 CODY.md 项目说明模板
cody init
```

---

## 命令概览

| 命令 | 说明 |
|------|------|
| `cody run` | 执行单次任务 |
| `cody chat` | 交互式对话 |
| `cody tui` | 全屏终端界面 |
| `cody sessions` | 会话管理 |
| `cody skills` | 技能管理 |
| `cody config` | 配置管理 |
| `cody init` | 初始化项目 |

---

## 1. run — 执行单次任务

执行一个 AI 任务并输出结果。

### 基本用法

```bash
cody run "创建一个 FastAPI hello world 应用"
```

### 完整参数

```bash
cody run "任务描述" \
  --model <模型名称> \
  --model-base-url <API 地址> \
  --model-api-key <API Key> \
  --coding-plan-key <阿里云 Coding Plan Key> \
  --coding-plan-protocol <openai|anthropic> \
  --thinking/--no-thinking \
  --thinking-budget <token 数> \
  --workdir <工作目录> \
  --verbose
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `prompt` | 任务描述（位置参数） | 必填 |
| `--model` | AI 模型名称 | 配置文件中的模型 |
| `--model-base-url` | 自定义 OpenAI 兼容 API 地址 | - |
| `--model-api-key` | 自定义模型 API Key | - |
| `--coding-plan-key` | 阿里云百炼 Coding Plan Key (`sk-sp-xxx`) | - |
| `--coding-plan-protocol` | Coding Plan 协议类型 | `openai` |
| `--thinking` | 启用思考模式（显示推理过程） | 配置文件中设置 |
| `--thinking-budget` | 思考模式最大 token 数 | - |
| `--workdir` | 工作目录（执行锚点，用于 config 加载和命令执行） | 当前目录 |
| `--allow-root` | 额外允许访问的目录（可重复，扩展访问边界） | - |
| `--verbose`, `-v` | 详细输出（显示工具调用结果） | `false` |

### 使用示例

#### 基础任务

```bash
# 创建文件
cody run "创建一个 Python 脚本，打印 Hello World"

# 重构代码
cody run "将 auth.py 重构为使用异步函数"

# 编写测试
cody run "为 user_service.py 编写单元测试"
```

#### 指定工作目录

```bash
# 在其他目录执行任务
cody run "修复测试失败" --workdir /path/to/project

# 使用绝对路径
cody run "添加日志功能" --workdir ~/projects/myapp
```

#### 多目录访问（Monorepo 场景）

```bash
# 同时访问 frontend 和 backend 目录
cody run --workdir /proj/frontend --allow-root /proj/backend "同步两个项目的类型定义"

# 允许访问共享库目录
cody run --workdir /proj/api --allow-root /shared/libs "修复引用"

# 多个额外目录
cody run --workdir /proj --allow-root /data/train --allow-root /data/test "运行评估"
```

#### 使用不同模型

```bash
# 使用智谱 GLM
cody run "写个排序算法" \
  --model glm-4 \
  --model-base-url https://open.bigmodel.cn/api/paas/v4/ \
  --model-api-key sk-xxx

# 使用阿里云通义千问
cody run "写个快速排序" \
  --model qwen-coder-plus \
  --model-base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --model-api-key sk-xxx

# 使用阿里云百炼 Coding Plan
cody run "写个二分查找" \
  --model qwen3.5 \
  --coding-plan-key sk-sp-xxx
```

#### 启用思考模式

```bash
# 启用思考（显示模型推理过程）
cody run --thinking "分析这个项目的架构问题"

# 设置思考 token 预算
cody run --thinking --thinking-budget 10000 "设计一个 REST API"

# 通过环境变量启用
export CODY_ENABLE_THINKING=true
export CODY_THINKING_BUDGET=10000
cody run "复杂任务分析"
```

#### 详细输出模式

```bash
# 显示工具调用结果
cody run -v "读取并分析 main.py"

# 输出示例：
# Model: anthropic:claude-sonnet-4-0
# Workdir: /home/user/project
#   → read_file(path='main.py')
#     [内容预览...]
# 分析结果...
```

### 输出说明

**正常输出:**
- 流式显示 AI 回复内容
- 工具调用以灰色显示（如 `→ read_file(path='main.py')`）
- 思考内容以暗色显示（如果启用）

**Verbose 模式额外显示:**
- 模型名称和工作目录
- 工具调用结果预览
- Token 使用统计

---

## 2. chat — 交互式对话

启动交互式 REPL 会话，支持多轮对话。

### 基本用法

```bash
cody chat
```

### 完整参数

```bash
cody chat \
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

| 参数 | 说明 |
|------|------|
| `--model` | AI 模型名称 |
| `--model-base-url` | 自定义 API 地址 |
| `--model-api-key` | 自定义 API Key |
| `--coding-plan-key` | 阿里云百炼 Coding Plan Key |
| `--coding-plan-protocol` | Coding Plan 协议类型 |
| `--thinking` | 启用思考模式 |
| `--thinking-budget` | 思考 token 预算 |
| `--workdir` | 工作目录（执行锚点） |
| `--allow-root` | 额外允许访问的目录（可重复） |
| `--session` | 恢复指定会话 |
| `--continue` | 继续上次会话 |

### 使用示例

#### 启动对话

```bash
# 基础对话
cody chat

# 指定模型
cody chat --model anthropic:claude-sonnet-4-0

# 指定工作目录
cody chat --workdir /path/to/project

# 启用思考模式
cody chat --thinking
```

#### 恢复会话

```bash
# 继续上次会话（自动查找最近会话）
cody chat --continue

# 恢复指定会话
cody chat --session abc123

# 在新目录继续会话
cody chat --continue --workdir /new/path
```

### 斜杠命令

在对话中输入 `/` 开头的命令：

| 命令 | 说明 |
|------|------|
| `/quit`, `/exit`, `/q` | 退出对话 |
| `/sessions` | 列出最近会话 |
| `/clear` | 清屏 |
| `/help` | 显示帮助 |

### 对话示例

```
╭────────────────────────────────────────────────────╮
│                  Cody Chat                          │
│  Model: anthropic:claude-sonnet-4-0                │
│  Workdir: /home/user/project                       │
│  Session: abc123                                   │
╰────────────────────────────────────────────────────╯
Type your message. Commands: /quit, /sessions, /clear, /help

You > 帮我创建一个 Flask 应用

  → write_file(path='app.py')
  → write_file(path='requirements.txt')

已创建 Flask 应用，包含以下文件：
- app.py: 主应用文件
- requirements.txt: 依赖列表

You > 添加一个 /health 端点

  → edit_file(path='app.py')

已添加 /health 端点，返回 {"status": "ok"}

You > /sessions
Recent sessions:
  abc123  Flask 应用开发                      4 msgs  2026-02-28
  def456  代码重构                            8 msgs  2026-02-27

You > /quit
Bye!
```

### 多行输入

支持使用反斜杠 continuation：

```
You > 帮我创建一个 FastAPI 应用，\
      包含用户认证、数据库连接、\
      和 JWT token 验证
```

---

## 3. tui — 全屏终端界面

启动基于 Textual 的全屏终端用户界面。

### 基本用法

```bash
cody tui
```

### 完整参数

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

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+N` | 新建会话 |
| `Ctrl+C` | 取消运行 / 退出 |
| `Ctrl+Q` | 退出应用 |
| `Enter` | 发送消息 |

### 斜杠命令

与 `chat` 命令相同：

| 命令 | 说明 |
|------|------|
| `/new` | 新建会话 |
| `/sessions` | 列出会话 |
| `/clear` | 清屏 |
| `/quit`, `/exit`, `/q` | 退出 |
| `/help` | 帮助 |

### 界面说明

```
┌─────────────────────────────────────────────────────┐
│  Header: Cody                            [Header]   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  You > 创建 Flask 应用                              │
│                                                     │
│  Cody > 已创建 Flask 应用...                        │
│         → write_file(path='app.py')                 │
│         → write_file(path='requirements.txt')       │
│                                                     │
│  [滚动区域 - 对话历史]                               │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Session: abc123 | Model: ... | Dir: project       │
├─────────────────────────────────────────────────────┤
│  You > [输入框]                                     │
├─────────────────────────────────────────────────────┤
│  Ctrl+N New  Ctrl+C Cancel  Ctrl+Q Quit  [Footer]  │
└─────────────────────────────────────────────────────┘
```

---

## 4. sessions — 会话管理

管理聊天会话（列表、查看、删除）。

### 子命令

```bash
cody sessions list    # 列出会话
cody sessions show    # 查看会话详情
cody sessions delete  # 删除会话
```

### sessions list

列出最近的聊天会话。

```bash
cody sessions list
cody sessions list --limit 10
```

**输出示例:**
```
Recent sessions:

  abc123  Flask 应用开发                      4 msgs  2026-02-28
  def456  代码重构                            8 msgs  2026-02-27
  ghi789  单元测试编写                        3 msgs  2026-02-26
```

### sessions show

查看会话的完整对话历史。

```bash
cody sessions show <session_id>
```

**输出示例:**
```
╭────────────────────────────────────────────────────╮
│            Session abc123                           │
│  Title: Flask 应用开发                             │
│  Model: anthropic:claude-sonnet-4-0                │
│  Workdir: /home/user/project                       │
│  Created: 2026-02-28T10:00:00                      │
│  Messages: 4                                       │
╰────────────────────────────────────────────────────╯

You: 帮我创建一个 Flask 应用

Cody: 已创建 Flask 应用，包含以下文件：
      - app.py: 主应用文件
      - requirements.txt: 依赖列表

You: 添加一个 /health 端点

Cody: 已添加 /health 端点...
```

### sessions delete

删除指定会话（需要确认）。

```bash
cody sessions delete <session_id>
```

**交互:**
```
Are you sure you want to delete this session? [y/N]: y
Deleted session: abc123
```

---

## 5. skills — 技能管理

管理 AI 技能（列表、查看、启用、禁用）。

### 子命令

```bash
cody skills list      # 列出技能
cody skills show      # 查看技能文档
cody skills enable    # 启用技能
cody skills disable   # 禁用技能
```

### skills list

列出所有可用技能。

```bash
cody skills list
```

**输出示例:**
```
Available Skills:

  [on] git        (builtin)
        Git version control operations...
  [on] github     (builtin)
        GitHub integration...
  [on] docker     (builtin)
        Docker container management...
  [off] python    (builtin)
        Python development...
```

### skills show

查看技能的完整文档。

```bash
cody skills show git
cody skills show docker
```

**输出示例:**
```
╭────────────────────────────────────────────────────╮
│                    git                              │
│                                                     │
│  # Git Operations                                   │
│                                                     │
│  Git version control operations using git CLI.     │
│                                                     │
│  ## Prerequisites                                   │
│  - Git must be installed: git --version             │
│  ...                                               │
╰────────────────────────────────────────────────────╯
```

### skills enable

启用一个技能。

```bash
cody skills enable python
```

**输出:**
```
Enabled skill: python
```

### skills disable

禁用一个技能。

```bash
cody skills disable docker
```

**输出:**
```
Disabled skill: docker
```

---

## 6. config — 配置管理

查看和修改配置。

### 子命令

```bash
cody config show    # 显示当前配置
cody config set     # 设置配置项
```

### config show

显示当前生效的配置（JSON 格式）。

```bash
cody config show
```

**输出示例:**
```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "model_base_url": null,
  "model_api_key": null,
  "enable_thinking": false,
  "thinking_budget": null,
  "skills": {
    "enabled": ["git", "github"],
    "disabled": []
  },
  "permissions": {
    "overrides": {},
    "default_level": "confirm"
  }
}
```

### config set

设置配置项。

```bash
# 设置模型
cody config set model "anthropic:claude-sonnet-4-0"

# 设置自定义 API 地址
cody config set model_base_url "https://..."

# 设置 API Key（不推荐，建议使用环境变量）
cody config set model_api_key "sk-..."
```

**输出:**
```
Set model = anthropic:claude-sonnet-4-0
```

> ⚠️ **安全提示**: API Key 建议通过环境变量设置（`CODY_MODEL_API_KEY`），不要写入配置文件。

---

## 7. init — 初始化项目

在当前目录创建 Cody 配置，并用 AI 分析项目后生成或更新 `CODY.md`。

```bash
cody init
```

可重复运行：`.cody/` 已存在时跳过 scaffold，`CODY.md` **始终**重新生成。

**创建/更新的文件:**
```
CODY.md            # 项目说明文件（AI 生成，每次 session 自动读取）
.cody/             # 首次运行时创建
├── config.json    # 项目配置文件
└── skills/        # 项目自定义技能目录
```

**首次运行输出:**
```
Initialized Cody in current directory
  Created .cody/
  Created .cody/skills/
  Created .cody/config.json
  Created CODY.md (AI-generated)
```

**重复运行输出（`.cody/` 已存在）:**
```
.cody directory already exists — skipping scaffold
Initialized Cody in current directory
  Updated CODY.md (AI-generated)
```

> **CODY.md** 是 Cody 的项目说明文件，每次启动 session 时自动注入到系统提示中。
> 项目演进后重新运行 `cody init` 即可更新。
> 详见 [CODY.md 说明](#codymd-项目说明文件)。

---

## 配置优先级

配置加载顺序（后加载覆盖先加载）：

1. **内置默认值** — Pydantic 模型默认值
2. **全局配置** — `~/.cody/config.json`
3. **项目配置** — `.cody/config.json`
4. **环境变量** — `CODY_*` 系列变量
5. **CLI 参数** — 命令行标志

### 环境变量列表

| 变量 | 说明 |
|------|------|
| `CODY_MODEL` | 模型名称 |
| `CODY_MODEL_BASE_URL` | 自定义 API 地址 |
| `CODY_MODEL_API_KEY` | 自定义 API Key |
| `CODY_CODING_PLAN_KEY` | 阿里云百炼 Coding Plan Key |
| `CODY_CODING_PLAN_PROTOCOL` | Coding Plan 协议 (`openai`/`anthropic`) |
| `CODY_ENABLE_THINKING` | 启用思考模式 (`true`/`false`) |
| `CODY_THINKING_BUDGET` | 思考 token 预算 |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `CLAUDE_OAUTH_TOKEN` | Claude OAuth Token |

---

## 支持模型

### 内置支持

| 提供商 | 模型示例 |
|--------|----------|
| Anthropic | `anthropic:claude-sonnet-4-0`, `anthropic:claude-opus-4-0` |
| OpenAI | `openai:gpt-4`, `openai:gpt-4-turbo` |
| Google | `google:gemini-pro` |
| DeepSeek | `deepseek:deepseek-coder` |

### OpenAI 兼容 API

任何 OpenAI 兼容的 API 都可以通过 `--model-base-url` 使用：

```bash
# 智谱 GLM
cody run "任务" \
  --model glm-4 \
  --model-base-url https://open.bigmodel.cn/api/paas/v4/

# 阿里通义千问
cody run "任务" \
  --model qwen-coder-plus \
  --model-base-url https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 阿里云百炼 Coding Plan

```bash
# OpenAI 协议
cody run "写个排序算法" \
  --model qwen3.5 \
  --coding-plan-key sk-sp-xxx

# Anthropic 协议
cody run "写个排序算法" \
  --model qwen3.5 \
  --coding-plan-key sk-sp-xxx \
  --coding-plan-protocol anthropic
```

---

## 工具集

Cody 提供 28+ 个 AI 工具，可在对话中自动使用：

### 文件操作
- `read_file` — 读取文件
- `write_file` — 写入文件
- `edit_file` — 精确编辑
- `list_directory` — 列出目录

### 搜索
- `grep` — 正则搜索内容
- `glob` — 通配符匹配文件
- `search_files` — 模糊搜索文件名
- `patch` — 应用 diff 补丁

### Shell
- `exec_command` — 执行命令

### 技能
- `list_skills` — 列出技能
- `read_skill` — 读取技能文档

### 子代理
- `spawn_agent` — 孵化子代理
- `get_agent_status` — 查询状态
- `kill_agent` — 终止代理

### Web
- `webfetch` — 抓取网页
- `websearch` — Web 搜索

### LSP
- `lsp_diagnostics` — 诊断信息
- `lsp_definition` — 跳转定义
- `lsp_references` — 查找引用
- `lsp_hover` — 悬停信息

### 文件历史
- `undo_file` — 撤销
- `redo_file` — 重做
- `list_file_changes` — 列出变更

### 任务管理
- `todo_write` — 写入任务
- `todo_read` — 读取任务

### 用户交互
- `question` — 向用户提问

---

## 最佳实践

### 1. 使用工作目录

始终使用 `--workdir` 明确指定项目目录：

```bash
# 推荐
cody run "重构 auth 模块" --workdir /path/to/project

# 不推荐（依赖当前目录）
cd /path/to/project && cody run "重构 auth 模块"
```

### 2. 会话复用

对于多轮对话，使用 `--continue` 或 `--session`：

```bash
# 第一次
cody chat --workdir /path/to/project

# 继续上次
cody chat --continue
```

### 3. 复杂任务使用思考模式

对于复杂分析任务，启用思考模式：

```bash
cody run --thinking "分析这个项目的架构问题并提出改进建议"
```

### 4. 使用技能

让 AI 了解特定领域的最佳实践：

```bash
# 启用相关技能
cody skills enable git
cody skills enable python

# 在任务中引用
cody run "按照 Python 最佳实践重构这个模块"
```

### 5. 详细模式调试

遇到问题时使用 `-v` 查看详细工具调用：

```bash
cody run -v "读取配置文件"
```

---

## 常见问题

### Q: 如何切换模型？

```bash
# 临时切换
cody run "任务" --model glm-4 --model-base-url ...

# 永久切换
cody config set model "glm-4"
```

### Q: 会话存储在哪里？

会话存储在 `~/.cody/sessions.db` (SQLite)。

### Q: 如何查看审计日志？

通过 RPC Server 的 `/audit` 端点，或直接查询 `~/.cody/audit.db`。

### Q: 工具执行失败怎么办？

1. 检查权限配置 (`cody config show`)
2. 使用 `-v` 查看详细错误
3. 检查工作目录是否正确

### Q: 如何自定义技能？

在 `.cody/skills/` 目录下创建技能目录和 `SKILL.md` 文件。

### Q: CODY.md 和 Skills 有什么区别？

| | CODY.md | Skills |
|---|---------|--------|
| **用途** | 描述项目上下文、约定 | 提供特定任务的操作步骤 |
| **格式** | 自由 Markdown | 标准化 SKILL.md |
| **触发** | 每次 session 自动加载 | 按需 `read_skill()` 调用 |
| **范围** | 项目级 + 用户级 | 全局 + 项目级 |

---

## CODY.md 项目说明文件

`CODY.md` 是 Cody 的项目说明文件，类似于 Claude Code 的 `CLAUDE.md`，
每次启动 session 时自动读取并注入到 AI 的系统提示中。

### 文件位置与加载顺序

两个位置的 CODY.md 都会被加载并合并（均可选）：

| 文件路径 | 说明 |
|----------|------|
| `~/.cody/CODY.md` | **全局**用户级说明（对所有项目生效） |
| `<workdir>/CODY.md` | **项目**级说明（仅对当前项目生效） |

两个文件都存在时，全局说明在前，项目说明在后，以 `---` 分隔。

### 生成模板

```bash
cody init
# 自动创建 CODY.md 模板
```

### 示例内容

```markdown
# CODY.md — Project Instructions

## Project Overview

这是一个 Python FastAPI 项目，提供 REST API 服务。

## Architecture

- `api/` — FastAPI 路由和端点
- `core/` — 业务逻辑
- `tests/` — pytest 测试

## Conventions

- 使用 ruff 做 lint，行宽 120
- 提交信息格式：`type(scope): description`
- 分支命名：`feature/xxx`、`fix/xxx`

## Development Commands

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check .
uvicorn api.main:app --reload
```
```

### 最佳实践

- **保持简短** — Cody 每次都会读取，内容越精简越好
- **重点突出** — 记录架构、约定、注意事项，而不是完整文档
- **定期更新** — 项目演进时同步更新 CODY.md
- **全局 vs 项目** — 通用偏好放全局，项目专属放项目根目录

---

**最后更新:** 2026-03-01
