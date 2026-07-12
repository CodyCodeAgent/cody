# Cody - HTTP API Documentation

## 概述

Cody 框架通过 Web Backend（FastAPI）提供 HTTP/WebSocket API，供外部系统集成。这是框架的四种运行方式之一。

> **推荐**：如果你的应用是 Python，优先使用 [Python SDK](SDK.md)（in-process，无需启动服务）。HTTP API 适用于非 Python 环境或需要远程访问的场景。

**Base URL:** `http://localhost:8000`

**版本：** 2.0.2

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
  "model": "deepseek-v4-flash",
  "model_base_url": null,
  "model_api_key": null,
  "skills": ["python", "git"],
  "session_id": "optional-session-id",
  "images": [
    {"data": "<base64>", "media_type": "image/png", "filename": "screenshot.png"}
  ]
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
| model_api_key | string | ❌ | 单请求 API Key（不推荐；生产环境应由服务端 secret manager 注入） |
| enable_thinking | bool | ❌ | 启用 thinking 模式（需模型支持） |
| thinking_budget | int | ❌ | thinking 最大 token 数（如 10000） |
| skills | string[] | ❌ | 启用的 Skills 列表 |
| session_id | string | ❌ | 会话 ID，用于多轮对话 |
| images | ImagePayload[] | ❌ | 图片附件列表（base64 编码），用于多模态输入 |
| max_tokens | int | ❌ | 熔断器：单次 run 最大累计 token 数（覆盖配置） |
| max_cost_usd | float | ❌ | 熔断器：单次 run 最大成本 USD（覆盖配置） |
| max_steps | int | ❌ | 熔断器：单次 run 最大工具调用步数（覆盖配置） |
| include_tools | string[] | ❌ | 只允许使用指定工具（与 exclude_tools 互斥） |
| exclude_tools | string[] | ❌ | 排除指定工具（与 include_tools 互斥） |

**ImagePayload 结构：**
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| data | string | ✅ | 图片 base64 编码数据 |
| media_type | string | ✅ | MIME 类型（image/png, image/jpeg 等）|
| filename | string | ❌ | 文件名 |

**使用自定义模型提供商（如智谱 GLM）：**
```json
{
  "prompt": "写一个排序算法",
  "model": "glm-4",
  "model_base_url": "https://open.bigmodel.cn/api/paas/v4/",
  "model_api_key": "your-api-key"
}
```

**使用自定义模型：**
```json
{
  "prompt": "写一个排序算法",
  "model": "qwen3.5",
  "model_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model_api_key": "your-api-key"
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

每个事件都包含 `session_id` 字段。第一个事件始终是 `session_start`，确保客户端在 AI 调用前就能拿到 session ID。

**事件类型：**
| 事件 | 说明 |
|------|------|
| session_start | 会话开始，始终是第一个事件（v1.11.0+），包含 `session_id` |
| thinking | 模型思考过程（增量），`content` 字段 |
| tool_call | 工具调用发起，包含 `tool_name`、`args`、`tool_call_id` |
| tool_result | 工具返回结果，包含 `tool_name`、`tool_call_id`、`result` |
| text_delta | 流式文本片段（增量），`content` 字段 |
| done | 任务完成，包含 `output`、`thinking`、`tool_traces`、`usage`、`metadata` |
| compact | 上下文压缩完成，包含 `original_messages`、`compacted_messages`、`estimated_tokens_saved` |
| prune | 选择性修剪完成，包含 `pruned_count`、`estimated_tokens_saved` |
| circuit_breaker | 熔断器触发，包含 `reason`、`tokens_used`、`cost_usd` |
| cancelled | 任务被取消（通过 `cancel_event`），无额外字段 |
| retry | 模型调用失败即将重试（v2.0.0+），包含 `attempt`、`max_attempts`、`error`。消费者应清空已缓冲的部分输出 |
| interaction_request | AI 请求人工输入，包含 `request_id`、`kind`、`prompt`、`options` |
| user_input_received | 用户主动输入已接收，包含 `content` |
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
| `save_memory` | 保存跨任务记忆（category + content）|

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

#### Projects 与 Tasks

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects` | GET | 列出项目 |
| `/api/projects` | POST | 创建项目、初始化 `.cody/` 并创建关联 session |
| `/api/projects/{project_id}` | GET/PUT/DELETE | 查询、更新或删除项目 |
| `/api/projects/{project_id}/init` | POST | 使用模型分析项目并生成/更新 `CODY.md` |
| `/api/projects/{project_id}/tasks` | GET/POST | 列出或创建开发任务 |
| `/api/tasks/{task_id}` | GET/PUT/DELETE | 查询、更新或删除任务 |

创建项目：

```json
{
  "name": "Cody",
  "description": "Agent Runtime",
  "workdir": "/path/to/project",
  "code_paths": []
}
```

创建 task 会在项目 Git 仓库中创建/切换 `branch_name`，并创建独立 session：

```json
{
  "name": "Fix runtime recovery",
  "branch_name": "fix/runtime-recovery"
}
```

项目或 task 不存在返回 404；请求字段不合法返回 422。`/init` 需要已配置可用模型。

Web 前端还提供两个项目化 WebSocket：`/ws/chat/{project_id}` 与
`/ws/chat/task/{task_id}`。两者使用项目/task 的 workdir 和 session，并从 canonical
RunEvent 投影兼容聊天事件。

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
      "model": "deepseek-v4-flash",
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
  "model": "deepseek-v4-flash",
  "workdir": "/path/to/project",
  "message_count": 2,
  "created_at": "2026-02-13T12:00:00",
  "updated_at": "2026-02-13T12:10:00",
  "messages": [
    {"role": "user", "content": "创建文件", "timestamp": "...", "images": [{"data": "<base64>", "media_type": "image/png", "filename": "screenshot.png"}]},
    {"role": "assistant", "content": "已创建", "timestamp": "...", "images": null}
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

### 7. 子 Agent 管理

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

### 8. 健康检查

#### GET /health 与 GET /api/health

两个端点返回相同服务状态。

**响应：**
```json
{
  "status": "ok",
  "version": "1.8.0"
}
```

---

### 9. 审计日志

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

生产服务通过 `CODY_AUTH_TYPE` 与 `CODY_AUTH_API_KEY`（或 OAuth token 环境变量）配置
认证。凭证不由 `/config` 持久化，也不会在 `GET /config` 返回。

Server 支持可选的认证中间件。配置 `auth` 后，所有非公开端点（`/health`, `/docs` 除外）都需要认证。

**API Key 模式：**
```bash
curl -H 'Authorization: Bearer cody_your_api_key' http://localhost:8000/run ...
```

未配置认证时，所有请求放行。

### WebSocket 认证

WebSocket 端点（`/ws` 和 `/ws/chat/{project_id}`）同样需要认证。连接时通过 URL 参数或 HTTP 头传递 token：

```text
ws://localhost:8000/ws?token=your_auth_token
```

或使用 `Authorization` 头：

```text
Authorization: Bearer your_auth_token
```

认证失败时，WebSocket 连接会被拒绝（close code 4001）。

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

## Canonical Runtime API

所有端点通过 `workdir` 连接与 CLI/TUI 相同的 durable Runtime stores。
生命周期、恢复语义和部署后端详见 [Runtime 使用与部署](RUNTIME.md)。

| 端点 | 方法 | 说明 |
|------|------|------|
| `/runtime/runs` | POST | 异步启动 canonical Run，返回 202 |
| `/runtime/runs` | GET | 分页列出 Runs |
| `/runtime/runs/{id}` | GET | Run 与 Step 详情 |
| `/runtime/runs/{id}/timeline` | GET | Timeline、checkpoint、artifact 关联视图 |
| `/runtime/runs/{id}/metrics` | GET | 时长、usage、重试、工具、gate 和 artifact 指标 |
| `/runtime/runs/{id}/checkpoints` | GET | Checkpoint 列表 |
| `/runtime/runs/{id}/artifacts` | GET | Run Artifacts |
| `/runtime/runs/{id}/pause` | POST | 请求安全边界暂停 |
| `/runtime/runs/{id}/cancel` | POST | 跨进程取消 |
| `/runtime/runs/{id}/resume` | POST | 恢复 waiting/paused Run |
| `/runtime/runs/{id}/retry` | POST | 重试 failed/cancelled Run |
| `/runtime/runs/{id}/recover` | POST | 恢复进程终止后孤立的 running Run |
| `/runtime/forks` | POST | 从 checkpoint fork |
| `/runtime/approvals` | GET | 查询审批 |
| `/runtime/approvals/{id}/approve` | POST | 批准 |
| `/runtime/approvals/{id}/reject` | POST | 拒绝 |
| `/runtime/artifacts/{id}` | GET | Artifact 详情 |
| `/runtime/audit` | GET | Runtime action audit |

启动示例：

```bash
curl -X POST http://localhost:8000/runtime/runs \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"修复测试", "workdir":"/path/to/project"}'
```

接口返回 202 后通过 Run 详情或 timeline 观察进度；取消和审批不会依赖发起请求的
HTTP 连接持续存在。

---

### WS /ws

建立 WebSocket 连接，用于实时双向交互。支持流式推送和中途取消。

**消息类型（客户端 → 服务端）：**

| 类型 | 说明 |
|------|------|
| `run` | 执行 Agent 任务 |
| `cancel` | 取消当前运行 |
| `user_input` | 用户主动发送消息（无需 AI 先提问），包含 `content` 字段 |
| `ping` | 心跳检测 |

**Run 消息：**
```json
{
  "type": "run",
  "data": {
    "prompt": "创建文件",
    "workdir": "/path",
    "model": "deepseek-v4-flash",
    "session_id": "abc123",
    "images": [
      {"data": "<base64>", "media_type": "image/png", "filename": "screenshot.png"}
    ]
  }
}
```

**Cancel 消息：**
```json
{"type": "cancel"}
```

**User Input 消息（用户随时输入，v1.11.0+）：**
```json
{"type": "user_input", "content": "先处理这个紧急 bug"}
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
| `done` | 任务完成，包含完整输出、thinking、tool_traces、usage、metadata |
| `circuit_breaker` | 熔断器触发（reason、tokens_used、cost_usd）|
| `retry` | 模型调用失败即将重试（attempt、max_attempts、error），消费者应清空部分输出 |
| `resuming` | 客户端重连时有正在运行的 stream，后续事件继续推送 |
| `interaction_request` | AI 请求人工输入（request_id、kind、prompt、options）|
| `user_input_received` | 用户主动输入已注入（content）|
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

## 新增端点（v2.0.0）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/config` | GET | 查看当前配置（隐藏密钥） |
| `/config` | PUT | 更新配置（模型、thinking、熔断器参数 `cb_max_tokens`/`cb_max_cost_usd`/`cb_max_steps`） |
| `/config/status` | GET | 配置就绪状态和缺失字段 |
| `/metrics` | GET | 运行时指标（total_runs、total_tokens、total_cost_usd、uptime_seconds） |
| `/skills` | GET | 列出所有 Skills |
| `/skills/{name}/enable` | POST | 启用 Skill |
| `/skills/{name}/disable` | POST | 禁用 Skill |

---

**最后更新：** 2026-07-12
