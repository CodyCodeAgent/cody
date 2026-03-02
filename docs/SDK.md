# Cody - SDK 使用文档

Cody 提供 Python SDK，用于在 Python 应用中直接使用 Cody 核心引擎。SDK 是 core 的 in-process 封装，无需 HTTP 服务。

---

## 目录

1. [Python SDK](#python-sdk)
2. [最佳实践](#最佳实践)

---

## Python SDK

### 安装

```bash
# 安装 cody 包（包含 SDK）
pip install cody-ai

# 或从源码安装
pip install -e .
```

### 快速开始

```python
from cody import AsyncCodyClient

# 异步客户端（推荐）— 无需 HTTP 服务
async with AsyncCodyClient() as client:
    result = await client.run("创建一个 hello.py 文件")
    print(result.output)
```

### 客户端类型

SDK 是 core 的 in-process 封装，直接导入核心模块，无需启动任何 HTTP 服务。

#### AsyncCodyClient（异步，推荐）

```python
from cody import AsyncCodyClient

async with AsyncCodyClient(
    workdir="/path/to/project",  # 工作目录，默认 cwd
    model="anthropic:claude-sonnet-4-0",  # 可选模型覆盖
    db_path="/path/to/sessions.db",  # 可选会话数据库路径
) as client:
    # 使用客户端
    result = await client.run("任务")
```

#### CodyClient（同步）

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

### 错误处理

```python
from cody import CodyError, CodyNotFoundError

try:
    result = await client.run("任务")
except CodyNotFoundError as e:
    print(f"资源不存在：{e.message}")
except CodyError as e:
    print(f"错误：{e.message}")
```

**错误类型：**
| 错误 | 说明 |
|------|------|
| `CodyError` | 基础错误类 |
| `CodyNotFoundError` | 资源不存在（会话/工具/技能）|

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

**最后更新:** 2026-03-02
