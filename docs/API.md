# Cody - RPC API Documentation

## 概述

Cody RPC Server 基于 FastAPI 构建，提供 RESTful API 接口。

**Base URL:** `http://localhost:8000`

**版本：** 1.3.0

---

## 接口列表

### 1. 运行 Agent

#### POST /run

执行 AI 任务并返回结果。支持通过 `session_id` 实现多轮对话。

**请求体：**
```json
{
  "prompt": "创建一个 FastAPI 项目",
  "workdir": "/path/to/project",
  "allowed_roots": [],
  "model": "anthropic:claude-sonnet-4-0",
  "model_base_url": null,
  "model_api_key": null,
  "claude_oauth_token": null,
  "skills": ["python", "git"],
  "session_id": "optional-session-id"
}
```

**参数说明：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| prompt | string | ✅ | 任务描述 |
| workdir | string | ❌ | 工作目录（执行锚点），默认当前目录 |
| allowed_roots | string[] | ❌ | 额外允许工具访问的目录（访问边界扩展），追加到配置文件设置之上 |
| model | string | ❌ | 模型名称，默认配置中的模型 |
| model_base_url | string | ❌ | 自定义 OpenAI 兼容 API 地址 |
| model_api_key | string | ❌ | 自定义模型提供商的 API Key |
| claude_oauth_token | string | ❌ | Claude OAuth token（替代 API Key，来自 `claude login`） |
| enable_thinking | bool | ❌ | 启用 thinking 模式（需模型支持） |
| thinking_budget | int | ❌ | thinking 最大 token 数（如 10000） |
| skills | string[] | ❌ | 启用的 Skills 列表 |
| session_id | string | ❌ | 会话 ID，用于多轮对话 |

**使用自定义模型提供商（如智谱 GLM）：**
```json
{
  "prompt": "写一个排序算法",
  "model": "glm-4",
  "model_base_url": "https://open.bigmodel.cn/api/paas/v4/",
  "model_api_key": "sk-your-key"
}
```

**使用 Claude OAuth token：**
```json
{
  "prompt": "写一个排序算法",
  "claude_oauth_token": "your-oauth-token"
}
```

**响应（成功）：**
```json
{
  "status": "success",
  "output": "已创建 FastAPI 项目",
  "thinking": "Let me analyze the requirements...",
  "tool_traces": [
    {"tool_name": "write_file", "args": {"path": "main.py"}, "result": "Written 200 bytes"}
  ],
  "session_id": "abc123",
  "usage": {
    "total_tokens": 230
  }
}
```

**HTTP 状态码：**
- `200` - 成功
- `400` - 请求参数错误（`INVALID_PARAMS`）
- `404` - 会话不存在（`SESSION_NOT_FOUND`）
- `500` - 服务器错误（`SERVER_ERROR`）

---

### 2. 流式运行

#### POST /run/stream

以 Server-Sent Events (SSE) 方式流式返回**结构化事件**。请求体与 `POST /run` 相同。

**响应（SSE）：**
```
data: {"type": "thinking", "content": "Let me analyze..."}

data: {"type": "tool_call", "tool_name": "read_file", "args": {"path": "main.py"}, "tool_call_id": "tc_1"}

data: {"type": "tool_result", "tool_name": "read_file", "tool_call_id": "tc_1", "result": "..."}

data: {"type": "text_delta", "content": "这是"}

data: {"type": "text_delta", "content": "文件内容"}

data: {"type": "done", "output": "这是文件内容", "thinking": "...", "tool_traces": [...], "usage": {"total_tokens": 230}}
```

带 session_id 时，每个事件都包含 `session_id` 字段。

**事件类型：**
| 事件 | 说明 |
|------|------|
| thinking | 模型思考过程（增量），`content` 字段 |
| tool_call | 工具调用发起，包含 `tool_name`、`args`、`tool_call_id` |
| tool_result | 工具返回结果，包含 `tool_name`、`tool_call_id`、`result` |
| text_delta | 流式文本片段（增量），`content` 字段 |
| done | 任务完成，包含 `output`、`thinking`、`tool_traces`、`usage` |
| error | 错误发生，包含结构化错误信息 |

**SSE 错误示例：**
```
data: {"type": "error", "error": {"code": "SERVER_ERROR", "message": "..."}}
```

---

### 3. 直接调用工具

#### POST /tool

直接调用某个工具，不经过 Agent。

**请求体：**
```json
{
  "tool": "read_file",
  "params": {
    "path": "README.md"
  },
  "workdir": "/path/to/project"
}
```

**响应：**
```json
{
  "status": "success",
  "result": "# Project Name\n\nDescription..."
}
```

**可用工具：**

| 工具 | 说明 |
|------|------|
| `read_file` | 读取文件 |
| `write_file` | 写入文件 |
| `edit_file` | 精确编辑文件 |
| `list_directory` | 列出目录内容 |
| `exec_command` | 执行 Shell 命令 |
| `grep` | 正则搜索文件内容 |
| `glob` | 通配符匹配文件 |
| `patch` | 应用 unified diff |
| `search_files` | 模糊搜索文件名 |
| `webfetch` | 抓取网页转 Markdown |
| `websearch` | Web 搜索 |
| `lsp_diagnostics` | LSP 诊断信息 |
| `lsp_definition` | 跳转到定义 |
| `lsp_references` | 查找引用 |
| `lsp_hover` | 悬停信息 |
| `undo_file` | 撤销上次文件修改 |
| `redo_file` | 重做上次撤销 |
| `list_file_changes` | 列出可撤销的文件修改 |
| `todo_write` | 创建/更新任务清单（JSON） |
| `todo_read` | 读取当前任务清单 |
| `question` | 向用户提结构化选择题 |

**HTTP 状态码：**
- `200` - 成功
- `400` - 参数无效（`INVALID_PARAMS`）
- `403` - 路径遍历攻击被拦截（`PERMISSION_DENIED`）
- `404` - 工具不存在（`TOOL_NOT_FOUND`）
- `500` - 工具执行错误（`TOOL_ERROR`）

---

### 4. Skill 管理

#### GET /skills

列出所有可用的 Skills。

**响应：**
```json
{
  "skills": [
    {
      "name": "git",
      "description": "Git Operations",
      "enabled": true,
      "source": "builtin"
    }
  ]
}
```

#### GET /skills/{name}

获取某个 Skill 的详细信息，包含 SKILL.md 文档内容。

**响应：**
```json
{
  "name": "git",
  "description": "Git Operations",
  "enabled": true,
  "source": "builtin",
  "documentation": "# Git Skill\n\n## Usage\n..."
}
```

**HTTP 状态码：**
- `404` - Skill 不存在（`SKILL_NOT_FOUND`）

---

### 5. Web API

#### GET /api/directories

浏览目录结构，返回子目录和文件列表。

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | ❌ | 目录路径，默认用户 home 目录 |

**响应：**
```json
{
  "path": "/home/user",
  "entries": [
    {"name": "projects", "is_dir": true},
    {"name": "file.txt", "is_dir": false}
  ]
}
```

**HTTP 状态码：**
- `200` - 成功
- `404` - 目录不存在（`INVALID_PARAMS`）
- `403` - 权限不足（`PERMISSION_DENIED`）

#### POST /api/projects/init

在指定目录初始化 `.cody/` 项目目录。

**请求体：**
```json
{
  "workdir": "/path/to/project"
}
```

**响应：**
```json
{
  "status": "success",
  "workdir": "/path/to/project"
}
```

**HTTP 状态码：**
- `200` - 成功
- `404` - 目录不存在（`INVALID_PARAMS`）
- `422` - 缺少 workdir 参数

---

### 6. 会话管理

#### POST /sessions

创建新会话。

**查询参数：**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| title | string | "New session" | 会话标题 |
| model | string | "" | 模型名称 |
| workdir | string | "" | 工作目录 |

**响应：**
```json
{
  "id": "abc123",
  "title": "New session",
  "model": "",
  "workdir": "",
  "message_count": 0,
  "created_at": "2026-02-13T12:00:00",
  "updated_at": "2026-02-13T12:00:00"
}
```

#### GET /sessions

列出最近的会话。

**查询参数：** `limit` (int, 默认 20)

**响应：**
```json
{
  "sessions": [
    {
      "id": "abc123",
      "title": "My session",
      "model": "anthropic:claude-sonnet-4-0",
      "workdir": "/path/to/project",
      "message_count": 4,
      "created_at": "2026-02-13T12:00:00",
      "updated_at": "2026-02-13T12:10:00"
    }
  ]
}
```

#### GET /sessions/{session_id}

获取会话详情，包含消息历史。

**响应：**
```json
{
  "id": "abc123",
  "title": "My session",
  "model": "anthropic:claude-sonnet-4-0",
  "workdir": "/path/to/project",
  "message_count": 2,
  "created_at": "2026-02-13T12:00:00",
  "updated_at": "2026-02-13T12:10:00",
  "messages": [
    {"role": "user", "content": "创建文件", "timestamp": "..."},
    {"role": "assistant", "content": "已创建", "timestamp": "..."}
  ]
}
```

#### DELETE /sessions/{session_id}

删除会话。

**响应：**
```json
{"status": "deleted", "id": "abc123"}
```

---

### 6. 子 Agent 管理

#### POST /agent/spawn

孵化一个子 Agent。

**请求体：**
```json
{
  "task": "研究 FastAPI 最佳实践",
  "type": "research",
  "timeout": 300
}
```

**参数：**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| task | string | - | 任务描述（必填）|
| type | string | "generic" | Agent 类型：code/research/test/generic |
| timeout | number | null | 超时时间（秒），null 使用默认值 300s |

**响应：**
```json
{
  "agent_id": "a1b2c3d4e5f6",
  "status": "pending",
  "created_at": "2026-02-13T12:00:00+00:00"
}
```

**HTTP 状态码：**
- `429` - 并发上限（`AGENT_LIMIT_REACHED`）
- `500` - Agent 错误（`AGENT_ERROR`）

#### GET /agent/{agent_id}

查询子 Agent 状态。

**响应：**
```json
{
  "agent_id": "a1b2c3d4e5f6",
  "status": "completed",
  "output": "FastAPI 最佳实践：\n1. ...",
  "error": null,
  "created_at": "2026-02-13T12:00:00+00:00",
  "completed_at": "2026-02-13T12:00:15+00:00"
}
```

**状态值：**
- `pending` - 等待中
- `running` - 运行中
- `completed` - 已完成
- `failed` - 失败
- `killed` - 已终止
- `timeout` - 超时

#### DELETE /agent/{agent_id}

终止子 Agent。

**响应：**
```json
{
  "agent_id": "a1b2c3d4e5f6",
  "killed": true,
  "status": "killed"
}
```

---

### 7. 健康检查

#### GET /health

检查服务状态。

**响应：**
```json
{
  "status": "ok",
  "version": "1.3.0"
}
```

---

### 8. 审计日志

#### GET /audit

查询审计日志条目。

**查询参数：**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| event | string | null | 按事件类型过滤（tool_call, file_write, file_edit, command_exec, api_request, auth_failure 等）|
| since | string | null | 起始时间（ISO 8601）|
| limit | number | 50 | 返回条数上限 |

**响应：**
```json
{
  "entries": [
    {
      "id": "a1b2c3d4e5f6",
      "timestamp": "2026-02-13T12:00:00+00:00",
      "event": "tool_call",
      "tool_name": "read_file",
      "args_summary": "path=hello.py",
      "result_summary": "Read 100 bytes",
      "session_id": null,
      "workdir": "/tmp/project",
      "success": true
    }
  ],
  "total": 42
}
```

---

## 认证

Server 支持可选的认证中间件。配置 `auth` 后，所有非公开端点（`/health`, `/docs` 除外）都需要认证。

**API Key 模式：**
```bash
curl -H 'Authorization: Bearer cody_your_api_key' http://localhost:8000/run ...
```

**Token 模式（OAuth）：**
```bash
curl -H 'Authorization: Bearer <signed-token>' http://localhost:8000/run ...
```

未配置认证时，所有请求放行。

## 速率限制

配置 `rate_limit.enabled = true` 后，Server 按客户端 IP 做滑动窗口限流。

**限流响应（HTTP 429）：**
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded"
  }
}
```

**响应头：**
- `X-RateLimit-Limit` — 窗口内最大请求数
- `X-RateLimit-Remaining` — 剩余可用请求数
- `Retry-After` — 限流时，需等待的秒数

---

## WebSocket API

### WS /ws

建立 WebSocket 连接，用于实时双向交互。支持流式推送和中途取消。

**消息类型（客户端 → 服务端）：**

| 类型 | 说明 |
|------|------|
| `run` | 执行 Agent 任务 |
| `cancel` | 取消当前运行 |
| `ping` | 心跳检测 |

**Run 消息：**
```json
{
  "type": "run",
  "data": {
    "prompt": "创建文件",
    "workdir": "/path",
    "model": "anthropic:claude-sonnet-4-0",
    "session_id": "abc123"
  }
}
```

**Cancel 消息：**
```json
{"type": "cancel"}
```

**Ping 消息：**
```json
{"type": "ping"}
```

**服务端事件（服务端 → 客户端）：**

| 事件 | 说明 |
|------|------|
| `start` | 任务开始，包含 session_id |
| `thinking` | 模型思考过程（增量） |
| `tool_call` | 工具调用发起 |
| `tool_result` | 工具返回结果 |
| `text_delta` | 流式文本片段（增量） |
| `done` | 任务完成，包含完整输出、thinking、tool_traces、usage |
| `error` | 错误，包含结构化错误信息 |
| `cancelled` | 任务已取消 |
| `pong` | 心跳响应 |

**事件示例：**
```json
{"type": "start", "session_id": "abc123"}
{"type": "thinking", "content": "Let me analyze..."}
{"type": "tool_call", "tool_name": "read_file", "args": {"path": "main.py"}, "tool_call_id": "tc_1"}
{"type": "tool_result", "tool_name": "read_file", "tool_call_id": "tc_1", "result": "..."}
{"type": "text_delta", "content": "这是文件内容"}
{"type": "done", "output": "这是文件内容", "thinking": "...", "tool_traces": [...], "usage": {"total_tokens": 230}}
{"type": "error", "error": {"code": "SERVER_ERROR", "message": "..."}}
{"type": "cancelled"}
{"type": "pong"}
```

---

## 结构化错误响应

所有 API 错误返回统一的结构化格式：

```json
{
  "error": {
    "code": "TOOL_NOT_FOUND",
    "message": "Tool not found: nonexistent",
    "details": {"tool": "nonexistent"}
  }
}
```

### 错误码

| 错误码 | HTTP 状态码 | 说明 |
|--------|------------|------|
| INVALID_PARAMS | 400 | 请求参数无效 |
| PERMISSION_DENIED | 403 | 权限不足（含路径遍历拦截）|
| TOOL_NOT_FOUND | 404 | 工具不存在 |
| SKILL_NOT_FOUND | 404 | Skill 不存在 |
| SESSION_NOT_FOUND | 404 | 会话不存在 |
| AGENT_NOT_FOUND | 404 | 子 Agent 不存在 |
| AGENT_LIMIT_REACHED | 429 | 子 Agent 并发上限 |
| RATE_LIMITED | 429 | 请求限流 |
| TOOL_ERROR | 500 | 工具执行错误 |
| AGENT_ERROR | 500 | 子 Agent 错误 |
| SERVER_ERROR | 500 | 服务器内部错误 |

---

## 使用示例

### Python SDK（推荐）

SDK 是 in-process 封装，直接调用核心引擎，无需启动 Server。

```python
from cody import AsyncCodyClient

async with AsyncCodyClient(workdir="/path/to/project") as client:
    # 一次性调用
    result = await client.run("创建 hello.py")
    print(result.output)

    # 多轮会话
    session = await client.create_session()
    r1 = await client.run("创建 Flask 项目", session_id=session.id)
    r2 = await client.run("添加 /health 端点", session_id=session.id)

    # 流式响应
    async for chunk in client.stream("解释这段代码"):
        print(chunk.content, end="")

    # 直接调工具
    result = await client.tool("read_file", {"path": "main.py"})
    print(result.result)
```

### curl

```bash
# 运行任务
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "创建 hello.py", "workdir": "/path/to/project"}'

# 流式运行
curl -N -X POST http://localhost:8000/run/stream \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "创建项目"}'

# 列出 Skills
curl http://localhost:8000/skills

# 健康检查
curl http://localhost:8000/health
```

---

## 未实现（计划中）

以下功能在 API 设计中规划，但尚未实现：

- **GET /config** / **PATCH /config** — 运行时配置管理
- **GET /metrics** — 服务指标
- **POST /skills/{name}/enable** / **disable** — Skill 启停 REST API

---

**最后更新：** 2026-02-28
