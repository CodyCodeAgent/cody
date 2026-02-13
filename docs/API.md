# Cody - RPC API Documentation

## 概述

Cody RPC Server 基于 FastAPI 构建，提供 RESTful API 接口。

**Base URL:** `http://localhost:8000`

**认证方式：** Bearer Token（可选）

---

## 接口列表

### 1. 运行 Agent

#### POST /run

执行 AI 任务并返回结果。

**请求体：**
```json
{
  "prompt": "创建一个 FastAPI 项目",
  "workdir": "/path/to/project",
  "model": "anthropic:claude-sonnet-4-0",
  "skills": ["python", "git"],
  "mcp_servers": ["github"],
  "stream": false,
  "context": {
    "files": ["README.md", "main.py"]
  }
}
```

**参数说明：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| prompt | string | ✅ | 任务描述 |
| workdir | string | ❌ | 工作目录，默认当前目录 |
| model | string | ❌ | 模型名称，默认配置中的模型 |
| skills | array | ❌ | 启用的 Skills |
| mcp_servers | array | ❌ | 启用的 MCP Servers |
| stream | boolean | ❌ | 是否流式返回，默认 false |
| context | object | ❌ | 额外上下文 |

**响应（成功）：**
```json
{
  "status": "success",
  "output": "已创建 FastAPI 项目，包含以下文件：\n- main.py\n- requirements.txt",
  "usage": {
    "input_tokens": 150,
    "output_tokens": 80,
    "total_tokens": 230,
    "requests": 2,
    "tool_calls": 3
  },
  "tool_calls": [
    {
      "tool": "write_file",
      "args": {"path": "main.py", "content": "..."},
      "result": "Written to main.py"
    }
  ],
  "duration_ms": 3500
}
```

**响应（失败）：**
```json
{
  "status": "error",
  "error": {
    "code": "TOOL_ERROR",
    "message": "Failed to write file: Permission denied",
    "details": {...}
  }
}
```

**HTTP 状态码：**
- `200` - 成功
- `400` - 请求参数错误
- `401` - 未授权
- `500` - 服务器错误

---

### 2. 流式运行

#### POST /run/stream

以 Server-Sent Events (SSE) 方式流式返回结果。

**请求体：**
```json
{
  "prompt": "创建项目并说明步骤",
  "workdir": "/path/to/project",
  "stream": true
}
```

**响应（SSE）：**
```
event: start
data: {"run_id": "abc123"}

event: text
data: {"content": "正在"}

event: text
data: {"content": "创建"}

event: tool_call
data: {"tool": "write_file", "args": {"path": "main.py"}}

event: tool_result
data: {"tool": "write_file", "result": "Written to main.py"}

event: text
data: {"content": "已完成"}

event: done
data: {"output": "已完成项目创建", "usage": {...}}
```

**事件类型：**
| 事件 | 说明 |
|------|------|
| start | 任务开始 |
| text | 文本输出 |
| thinking | 思考过程（如果模型支持）|
| tool_call | 工具调用 |
| tool_result | 工具返回 |
| error | 错误发生 |
| done | 任务完成 |

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
  "result": "# Project Name\n\nDescription...",
  "duration_ms": 10
}
```

**可用工具：**
- `read_file`
- `write_file`
- `edit_file`
- `list_directory`
- `exec_command`
- `git_status`
- `git_diff`
- `git_commit`

---

### 4. Skill 管理

#### GET /skills

列出所有可用的 Skills。

**响应：**
```json
{
  "skills": [
    {
      "name": "github",
      "description": "GitHub CLI integration",
      "enabled": true,
      "source": "project",
      "path": "/path/to/.cody/skills/github"
    },
    {
      "name": "docker",
      "description": "Docker operations",
      "enabled": false,
      "source": "global",
      "path": "~/.cody/skills/docker"
    }
  ]
}
```

#### GET /skills/{name}

获取某个 Skill 的详细信息。

**响应：**
```json
{
  "name": "github",
  "description": "GitHub CLI integration",
  "enabled": true,
  "source": "project",
  "documentation": "# GitHub Skill\n\n## Usage\n...",
  "examples": [
    "gh issue create --title 'Bug' --body 'Description'"
  ]
}
```

#### POST /skills/{name}/enable

启用某个 Skill。

**响应：**
```json
{
  "status": "success",
  "message": "Skill 'github' enabled"
}
```

#### POST /skills/{name}/disable

禁用某个 Skill。

---

### 5. 子 Agent 管理

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
| 参数 | 类型 | 说明 |
|------|------|------|
| task | string | 任务描述 |
| type | string | Agent 类型：code/research/test/generic |
| timeout | number | 超时时间（秒） |

**响应：**
```json
{
  "agent_id": "sub_abc123",
  "status": "running",
  "created_at": "2026-01-28T01:00:00Z"
}
```

#### GET /agent/{agent_id}

查询子 Agent 状态。

**响应：**
```json
{
  "agent_id": "sub_abc123",
  "status": "completed",
  "result": "FastAPI 最佳实践：\n1. ...\n2. ...",
  "usage": {...},
  "duration_ms": 15000,
  "created_at": "2026-01-28T01:00:00Z",
  "completed_at": "2026-01-28T01:00:15Z"
}
```

**状态值：**
- `pending` - 等待中
- `running` - 运行中
- `completed` - 已完成
- `failed` - 失败
- `killed` - 已终止

#### DELETE /agent/{agent_id}

终止子 Agent。

---

### 6. 配置管理

#### GET /config

获取当前配置。

**响应：**
```json
{
  "model": "anthropic:claude-sonnet-4-0",
  "skills": {
    "enabled": ["github", "docker"],
    "disabled": []
  },
  "mcp": {
    "servers": [...]
  }
}
```

#### PATCH /config

更新配置。

**请求体：**
```json
{
  "model": "anthropic:claude-opus-4-5",
  "skills": {
    "enabled": ["github", "docker", "python"]
  }
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
  "version": "0.1.0",
  "uptime": 3600,
  "active_agents": 2
}
```

#### GET /metrics

获取服务指标（可选）。

**响应：**
```json
{
  "requests_total": 150,
  "requests_success": 145,
  "requests_failed": 5,
  "avg_duration_ms": 2500,
  "tokens_used": 50000
}
```

---

## WebSocket API ✅ 已实现

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
| `text` | 流式文本片段 |
| `done` | 任务完成，包含完整输出 |
| `error` | 错误，包含结构化错误信息 |
| `cancelled` | 任务已取消 |
| `pong` | 心跳响应 |

**事件示例：**
```json
{"type": "start", "session_id": "abc123"}
{"type": "text", "content": "正在创建..."}
{"type": "done", "output": "完成创建"}
{"type": "error", "error": {"code": "SERVER_ERROR", "message": "..."}}
{"type": "cancelled"}
{"type": "pong"}
```

---

## 结构化错误响应 ✅ 已实现

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
| AUTH_FAILED | 401 | 认证失败 |
| PERMISSION_DENIED | 403 | 权限不足 |
| TOOL_NOT_FOUND | 404 | 工具不存在 |
| SKILL_NOT_FOUND | 404 | Skill 不存在 |
| SESSION_NOT_FOUND | 404 | 会话不存在 |
| AGENT_NOT_FOUND | 404 | 子 Agent 不存在 |
| AGENT_LIMIT_REACHED | 429 | 子 Agent 并发上限 |
| MODEL_ERROR | 500 | 模型调用错误 |
| TOOL_ERROR | 500 | 工具执行错误 |
| AGENT_ERROR | 500 | 子 Agent 错误 |
| MCP_ERROR | 500 | MCP 通信错误 |
| TIMEOUT | 500 | 超时 |
| SERVER_ERROR | 500 | 服务器内部错误 |

SSE 流中的错误也使用结构化格式：
```
data: {"type": "error", "error": {"code": "SERVER_ERROR", "message": "..."}}
```

---

## 认证（可选）

如果启用认证，需要在请求头中包含 Token：

```
Authorization: Bearer <token>
```

获取 Token：
```bash
cody auth token
```

---

## 使用示例

### Python

```python
import requests

# 运行任务
response = requests.post(
    'http://localhost:8000/run',
    json={
        'prompt': '创建 hello.py',
        'workdir': '/path/to/project'
    }
)

result = response.json()
print(result['output'])
```

### JavaScript

```javascript
// 运行任务
const response = await fetch('http://localhost:8000/run', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    prompt: '创建 hello.py',
    workdir: '/path/to/project'
  })
});

const result = await response.json();
console.log(result.output);
```

### curl

```bash
# 运行任务
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "创建 hello.py",
    "workdir": "/path/to/project"
  }'

# 流式运行
curl -N -X POST http://localhost:8000/run/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "创建项目",
    "stream": true
  }'
```

---

## 性能考虑

**并发限制：**
- 默认最大并发请求：100
- 可通过配置调整

**超时设置：**
- 默认请求超时：60秒
- 长任务建议使用子 Agent

**速率限制：**
- 默认每分钟 60 请求
- 可通过配置调整

---

**最后更新：** 2026-02-13
