# Cody - SDK 使用文档

Cody 提供统一的 Python SDK（`cody.sdk`），用于在 Python 应用中直接使用 Cody 核心引擎。SDK 直接包装 core，无需 HTTP 服务。

> **架构说明**：`cody.sdk` 是唯一的 SDK 实现，直接包装 `cody.core`（单层）。`cody.client` 模块保留为向后兼容 shim，re-export 所有 SDK 符号。

---

## 目录

1. [快速开始](#快速开始)
2. [三种创建方式](#三种创建方式)
3. [核心方法](#核心方法)
4. [事件系统](#事件系统)
5. [指标收集](#指标收集)
6. [便捷方法](#便捷方法)
7. [错误处理](#错误处理)
8. [最佳实践](#最佳实践)

---

## 快速开始

### 安装

```bash
# 只装核心 SDK（4 个依赖）
pip install cody-ai

# 完整安装（包含 CLI、TUI、Web）
pip install cody-ai[all]
```

### 最简示例

```python
from cody import AsyncCodyClient

# 异步客户端（推荐）— 无需 HTTP 服务
async with AsyncCodyClient() as client:
    result = await client.run("创建一个 hello.py 文件")
    print(result.output)
```

### 导入路径

以下三种导入方式完全等价：

```python
from cody import AsyncCodyClient           # 推荐
from cody.sdk import AsyncCodyClient       # 完整路径
from cody.client import AsyncCodyClient    # 向后兼容
```

## 三种创建方式

```python
from cody.sdk import AsyncCodyClient, Cody, config

# 1. Builder 模式（推荐）
client = (
    Cody()
    .workdir("/path/to/project")
    .model("anthropic:claude-sonnet-4-0")
    .api_key("sk-xxx")
    .thinking(True, budget=10000)
    .enable_metrics()
    .enable_events()
    .build()
)

# 2. 直接构造
client = AsyncCodyClient(
    workdir="/path/to/project",
    model="anthropic:claude-sonnet-4-0",
    db_path="/path/to/sessions.db",
)

# 3. Config 对象
cfg = config(model="anthropic:claude-sonnet-4-0", workdir=".", enable_thinking=True)
client = AsyncCodyClient(config=cfg)
```

### CodyClient（同步）

```python
from cody import CodyClient

with CodyClient(workdir="/path/to/project") as client:
    result = client.run("任务")
```

### 核心方法

#### 1. run() — 执行任务

```python
# 异步
result = await client.run(
    "创建一个 FastAPI 项目",
    session_id="abc123",  # 可选，用于多轮对话
)

# 同步
result = client.run("创建一个 FastAPI 项目")

print(result.output)        # 输出内容
print(result.session_id)    # 会话 ID
print(result.usage.total_tokens)  # Token 使用量
```

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | str | ✅ | 任务描述 |
| `session_id` | str | ❌ | 会话 ID（多轮对话）|

> **注意：** `workdir` 和 `model` 在构造函数中设置，不支持 per-call 覆盖。

**返回：** `RunResult` 对象
```python
@dataclass
class RunResult:
    output: str
    session_id: Optional[str]
    usage: Usage  # input_tokens, output_tokens, total_tokens
```

---

#### 2. stream() — 流式执行

```python
# 异步
async for chunk in client.stream("解释这段代码"):
    print(chunk.content, end="")

# 同步（注意：同步版本会一次性返回所有 chunks 的列表，非真正流式）
for chunk in client.stream("解释这段代码"):
    print(chunk.content, end="")
```

**流式事件类型：**
| 类型 | 说明 |
|------|------|
| `text_delta` | 文本内容（增量） |
| `thinking` | 思考内容（增量） |
| `tool_call` | 工具调用 |
| `tool_result` | 工具结果 |
| `done` | 任务完成 |
| `compact` | 上下文压缩 |

**完整示例：**
```python
async with AsyncCodyClient() as client:
    async for chunk in client.stream("创建 Flask 应用"):
        if chunk.type == "text_delta":
            print(chunk.content, end="")
        elif chunk.type == "done":
            print("\n✅ 完成")
```

---

#### 3. tool() — 直接调用工具

```python
# 读取文件
result = await client.tool("read_file", {"path": "main.py"})
print(result.result)

# 执行命令
result = await client.tool("exec_command", {"command": "ls -la"})
print(result.result)

# 列出目录
result = await client.tool("list_directory", {"path": "."})
print(result.result)
```

**可用工具：**
- `read_file`, `write_file`, `edit_file`, `list_directory`
- `grep`, `glob`, `search_files`, `patch`
- `exec_command`
- `webfetch`, `websearch`
- `lsp_diagnostics`, `lsp_definition`, `lsp_references`, `lsp_hover`
- `todo_write`, `todo_read`
- `undo_file`, `redo_file`, `list_file_changes`
- 等等（28+ 个工具）

---

#### 4. 会话管理

```python
# 创建会话
session = await client.create_session(
    title="My Project",
    model="anthropic:claude-sonnet-4-0",
    workdir="/path/to/project",
)

# 多轮对话
r1 = await client.run("创建 Flask 应用", session_id=session.id)
r2 = await client.run("添加 /health 端点", session_id=session.id)
r3 = await client.run("添加用户认证", session_id=session.id)

# 列出会话
sessions = await client.list_sessions(limit=10)
for s in sessions:
    print(f"{s.id}: {s.title}")

# 获取会话详情（包含消息历史）
detail = await client.get_session(session.id)
for msg in detail.messages:
    print(f"{msg['role']}: {msg['content']}")

# 删除会话
await client.delete_session(session.id)
```

---

#### 5. 技能管理

```python
# 列出技能
skills = await client.list_skills()
for skill in skills:
    print(f"{skill['name']}: {skill['description']}")

# 获取技能文档
skill = await client.get_skill("git")
print(skill['documentation'])
```

---

#### 6. 健康检查

```python
health = await client.health()
print(f"Status: {health['status']}, Version: {health['version']}")
```

---

### 完整示例

#### 示例 1：单次任务

```python
import asyncio
from cody import AsyncCodyClient

async def main():
    async with AsyncCodyClient(workdir="/tmp/myproject") as client:
        result = await client.run("创建一个 Python 脚本，打印 Hello World")
        print(result.output)

asyncio.run(main())
```

#### 示例 2：多轮对话

```python
import asyncio
from cody import AsyncCodyClient

async def main():
    async with AsyncCodyClient() as client:
        # 创建会话
        session = await client.create_session(title="Flask 开发")
        
        # 第一轮：创建应用
        r1 = await client.run(
            "创建一个 Flask 应用",
            session_id=session.id,
        )
        print(r1.output)
        
        # 第二轮：添加端点
        r2 = await client.run(
            "添加一个 /health 端点",
            session_id=session.id,
        )
        print(r2.output)
        
        # 第三轮：添加认证
        r3 = await client.run(
            "添加 JWT 用户认证",
            session_id=session.id,
        )
        print(r3.output)

asyncio.run(main())
```

#### 示例 3：流式输出 + 错误处理

```python
import asyncio
from cody import AsyncCodyClient, CodyError

async def main():
    async with AsyncCodyClient() as client:
        try:
            async for chunk in client.stream("分析这个项目"):
                if chunk.type == "text_delta":
                    print(chunk.content, end="", flush=True)
                elif chunk.type == "done":
                    print("\n✅ 完成")
        except CodyError as e:
            print(f"错误：{e.message}")

asyncio.run(main())
```

#### 示例 4：工具调用

```python
import asyncio
from cody import AsyncCodyClient

async def main():
    async with AsyncCodyClient() as client:
        # 读取文件
        file_result = await client.tool(
            "read_file",
            {"path": "README.md"},
        )
        print(file_result.result[:200])
        
        # 搜索内容
        grep_result = await client.tool(
            "grep",
            {"pattern": "def main", "include": "*.py"},
        )
        print(grep_result.result)
        
        # 执行命令
        cmd_result = await client.tool(
            "exec_command",
            {"command": "python3 --version"},
        )
        print(cmd_result.result)

asyncio.run(main())
```

---

## 事件系统

```python
from cody.sdk import Cody, EventType

client = Cody().workdir(".").enable_events().build()

# 注册事件处理器
client.on(EventType.TOOL_CALL, lambda e: print(f"Tool: {e.tool_name}"))
client.on(EventType.RUN_END, lambda e: print(f"Done: {e.result[:50]}"))

async with client:
    await client.run("Read README.md")
```

**事件类型：**

| 事件 | 说明 |
|------|------|
| `RUN_START` / `RUN_END` / `RUN_ERROR` | 任务生命周期 |
| `TOOL_CALL` / `TOOL_RESULT` / `TOOL_ERROR` | 工具调用 |
| `THINKING_START` / `THINKING_CHUNK` / `THINKING_END` | 思考过程 |
| `STREAM_START` / `STREAM_CHUNK` / `STREAM_END` | 流式输出 |
| `SESSION_CREATE` / `SESSION_CLOSE` | 会话管理 |
| `CONTEXT_COMPACT` | 上下文压缩 |

## 指标收集

```python
from cody.sdk import Cody

client = Cody().workdir(".").enable_metrics().build()

async with client:
    await client.run("Analyze this project")

    metrics = client.get_metrics()
    print(f"Total tokens: {metrics['total_tokens']}")
    print(f"Tool calls: {metrics['total_tool_calls']}")
    print(f"Duration: {metrics['total_duration']:.2f}s")
```

## 便捷方法

```python
async with client:
    # 文件操作
    content = await client.read_file("main.py")
    await client.write_file("hello.py", "print('hello')")
    await client.edit_file("main.py", "old_text", "new_text")

    # 搜索
    files = await client.glob("**/*.py")
    matches = await client.grep("def main", include="*.py")

    # 命令执行
    output = await client.exec_command("ls -la")

    # LSP
    diags = await client.lsp_diagnostics("main.py")
    defn = await client.lsp_definition("main.py", line=10, column=5)
```

## 错误处理

```python
from cody.sdk import (
    CodyError,           # 基础错误
    CodyModelError,      # 模型 API 错误
    CodyToolError,       # 工具执行错误
    CodyPermissionError, # 权限不足
    CodyNotFoundError,   # 资源不存在
    CodyRateLimitError,  # 速率限制
    CodyConfigError,     # 配置错误
    CodyTimeoutError,    # 超时
    CodyConnectionError, # 连接错误
    CodySessionError,    # 会话错误
)

try:
    result = await client.run("task")
except CodyToolError as e:
    print(f"Tool {e.details['tool_name']} failed: {e.message}")
except CodyRateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
except CodyError as e:
    print(f"[{e.code}] {e.message}")
```

## 示例文件

SDK 提供 4 个完整示例（`cody/sdk/examples/`）：

| 文件 | 说明 |
|------|------|
| `basic.py` | 三种创建方式 + 多轮会话 |
| `streaming.py` | 流式输出消费 |
| `events_demo.py` | 事件钩子 + 指标 |
| `tools_demo.py` | 直接工具调用 |

---

## 最佳实践

### 1. 使用上下文管理器

```python
# 推荐：自动清理资源
async with AsyncCodyClient() as client:
    result = await client.run("任务")

# 不推荐：需要手动关闭
client = AsyncCodyClient()
result = await client.run("任务")
await client.close()
```

### 2. 使用流式处理大任务

```python
# 对于可能耗时较长的任务，使用流式可以实时看到进度
async for chunk in client.stream("分析整个项目"):
    if chunk.type == "text_delta":
        print(chunk.content, end="", flush=True)
```

### 3. 会话复用

```python
# 多轮对话使用同一个 session_id
session = await client.create_session()
await client.run("创建项目", session_id=session.id)
await client.run("添加功能", session_id=session.id)
await client.run("修复 bug", session_id=session.id)
```

### 4. 并发请求

```python
# Python asyncio 并发
async with asyncio.TaskGroup() as tg:
    task1 = tg.create_task(client.run("任务 1"))
    task2 = tg.create_task(client.run("任务 2"))
```

---

## API 参考

### Python SDK

| 类/函数 | 说明 |
|--------|------|
| `AsyncCodyClient` | 异步客户端 |
| `CodyClient` | 同步客户端 |
| `client.run()` | 执行任务 |
| `client.stream()` | 流式执行 |
| `client.tool()` | 调用工具 |
| `client.create_session()` | 创建会话 |
| `client.list_sessions()` | 列出会话 |
| `client.get_session()` | 获取会话详情 |
| `client.delete_session()` | 删除会话 |
| `client.list_skills()` | 列出技能 |
| `client.get_skill()` | 获取技能文档 |
| `client.health()` | 健康检查 |

---

**最后更新:** 2026-03-04
