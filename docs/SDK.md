# Cody SDK - Python SDK 使用文档

Cody 是一个开源 AI 编程助手框架（Open-source AI Coding Agent Framework）。**Python SDK（`cody.sdk`）是使用 Cody 框架的首选方式**——它直接包装 `cody.core` 引擎，在你的 Python 应用中以 in-process 方式运行，无需启动 HTTP 服务、无需部署额外进程。

无论你是构建自动化脚本、IDE 插件、CI/CD 流水线还是自己的 AI 编程产品，SDK 都提供了完整的 API 来驱动 Cody 的全部能力：Agent 执行、流式输出、工具调用、多模态 Prompt、技能管理、事件钩子与指标收集。

> **架构说明**：`cody.sdk` 是唯一的 SDK 实现，直接包装 `cody.core`（单层，零开销）。`cody.client` 模块保留为向后兼容 shim，re-export 所有 SDK 符号。

---

## 目录

1. [快速开始](#快速开始)
2. [四种创建方式](#四种创建方式)
3. [核心方法](#核心方法)
4. [多模态 Prompt](#多模态-prompt)
5. [思考模式](#思考模式)
6. [多工作目录与 allowed_roots](#多工作目录与-allowed_roots)
7. [技能管理](#技能管理)
8. [事件系统](#事件系统)
9. [指标收集](#指标收集)
10. [MCP 集成](#mcp-集成)
11. [熔断器（Circuit Breaker）](#熔断器circuit-breaker)
12. [结构化输出（Structured Output）](#结构化输出structured-output)
13. [人工交互（Human Interaction）](#人工交互human-interaction)
14. [项目记忆（Project Memory）](#项目记忆project-memory)
15. [便捷方法](#便捷方法)
16. [错误处理](#错误处理)
17. [最佳实践](#最佳实践)
18. [API 参考](#api-参考)

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

### 环境变量配置

SDK 支持通过环境变量配置模型，无需在代码中硬编码：

```bash
export CODY_MODEL=qwen3.5-plus
export CODY_MODEL_API_KEY=sk-xxx
export CODY_MODEL_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
```

配置优先级（从高到低）：代码参数 > 环境变量 > 项目配置文件 > 全局配置文件 > 默认值

> **注意**：`AsyncCodyClient()` 不传 model 参数时会使用环境变量，不会使用 SDK 默认模型覆盖。

## 四种创建方式

```python
from cody.sdk import AsyncCodyClient, Cody, config

# 1. Builder 模式（推荐）
client = (
    Cody()
    .workdir("/path/to/project")
    .model("claude-sonnet-4-0")
    .api_key("sk-ant-xxx")
    .thinking(True, budget=10000)
    .allowed_roots(["/path/to/project", "/shared/libs"])
    .enable_metrics()
    .enable_events()
    .build()
)

# 2. 直接构造
client = AsyncCodyClient(
    workdir="/path/to/project",
    model="claude-sonnet-4-0",
    api_key="sk-ant-xxx",
    base_url="https://api.example.com/v1",
    db_path="/path/to/sessions.db",
)

# 3. Config 对象
cfg = config(
    model="claude-sonnet-4-0",
    workdir=".",
    api_key="sk-ant-xxx",
    enable_thinking=True,
    thinking_budget=10000,
    allowed_roots=["/path/to/project", "/shared/libs"],
)
client = AsyncCodyClient(config=cfg)
```

### 连接第三方模型提供商

通过 `base_url` + `api_key` 连接任何 OpenAI 兼容 API：

```python
# 智谱 GLM
client = (
    Cody()
    .workdir("/path/to/project")
    .model("glm-4")
    .base_url("https://open.bigmodel.cn/api/paas/v4/")
    .api_key("your-zhipu-api-key")
    .build()
)

# 通义千问（阿里云百炼）
client = (
    Cody()
    .workdir("/path/to/project")
    .model("qwen-plus")
    .base_url("https://dashscope.aliyuncs.com/compatible-mode/v1")
    .api_key("sk-xxx")
    .build()
)

# DeepSeek
client = (
    Cody()
    .workdir("/path/to/project")
    .model("deepseek-chat")
    .base_url("https://api.deepseek.com/v1")
    .api_key("sk-xxx")
    .build()
)

# 直接构造方式同样支持
client = AsyncCodyClient(
    workdir="/path/to/project",
    model="glm-4",
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key="your-zhipu-api-key",
)
```

> **说明**：`base_url` 指向 OpenAI 兼容的 API 地址，必须配置。

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
| `prompt` | `str` / `MultimodalPrompt` | 是 | 任务描述（支持纯文本或多模态） |
| `session_id` | str | 否 | 会话 ID（多轮对话）|

> **注意：** `workdir` 和 `model` 在构造函数中设置，不支持 per-call 覆盖。

**返回：** `RunResult` 对象
```python
@dataclass
class RunResult:
    output: str
    session_id: Optional[str]   # 自动创建（首次调用也会返回）
    usage: Usage                # input_tokens, output_tokens, total_tokens
    thinking: Optional[str]     # 思考内容（启用思考模式时）
```

> **v1.7.1 变更**：`run()` 现在自动创建 session，首次调用即返回 `session_id`，无需手动调用 `create_session()`。

---

#### 2. stream() / run_stream() — 流式执行

`stream()` 和 `run_stream()` 完全等价（`run_stream` 是 `stream` 的别名）。

**参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | `str` / `MultimodalPrompt` | 是 | 任务描述 |
| `session_id` | str | 否 | 会话 ID（多轮对话）|
| `cancel_event` | `asyncio.Event` | 否 | 取消信号（v1.10.3+），设置后终止流并 yield `cancelled` 事件 |

```python
# 异步
async for chunk in client.stream("解释这段代码"):
    print(chunk.content, end="")

# 等价写法
async for chunk in client.run_stream("解释这段代码"):
    print(chunk.content, end="")

# 同步（注意：同步版本会一次性返回所有 chunks 的列表，非真正流式）
for chunk in client.stream("解释这段代码"):
    print(chunk.content, end="")
```

**StreamChunk 字段：**

```python
@dataclass
class StreamChunk:
    type: str                         # 事件类型（见下表）
    content: str                      # 文本内容
    session_id: Optional[str]         # 会话 ID
    tool_name: Optional[str]          # 工具名称（type="tool_call" / "tool_result" 时）
    args: Optional[dict]              # 工具参数（type="tool_call" 时）
    tool_call_id: Optional[str]       # 工具调用 ID（type="tool_call" / "tool_result" 时）
    usage: Optional[Usage]            # Token 用量（type="done" 时）
    # v1.7.4+ compact 事件详情
    original_messages: int            # 压缩前消息数（type="compact" 时）
    compacted_messages: int           # 压缩后消息数（type="compact" 时）
    estimated_tokens_saved: int       # 估计节省的 token 数（type="compact" 时）
    # v1.7.4+ done 事件消息历史
    message_history: Optional[list]   # 完整对话历史（type="done" 时）
    # 人工交互事件详情（type="interaction_request" 时）
    request_id: Optional[str]         # 交互请求 ID，用于 submit_interaction() 匹配
    interaction_kind: Optional[str]   # 交互类型："question" / "confirm" / "feedback"
    options: Optional[list[str]]      # 可选项列表
```

**流式事件类型：**

| 类型 | 说明 | 特有字段 |
| ---- | ---- | -------- |
| `session_start` | 会话开始，始终是第一个事件（v1.11.0+） | `session_id` |
| `text_delta` | 文本内容（增量） | `content` |
| `thinking` | 思考内容（增量） | `content` |
| `tool_call` | 工具调用 | `tool_name`, `args`, `tool_call_id` |
| `tool_result` | 工具结果 | `content`（结果文本）, `tool_name`, `tool_call_id` |
| `done` | 任务完成 | `usage`（Token 用量） |
| `cancelled` | 任务被取消（v1.10.3+） | — |
| `compact` | 上下文压缩 | — |
| `circuit_breaker` | 熔断器触发，任务终止 | `content`（原因描述） |
| `interaction_request` | 需要人工输入 | `request_id`, `interaction_kind`, `options`, `content`（提示文本） |

**完整示例：**
```python
async with AsyncCodyClient() as client:
    async for chunk in client.run_stream("创建 Flask 应用"):
        if chunk.type == "session_start":
            print(f"Session: {chunk.session_id}")
        elif chunk.type == "text_delta":
            print(chunk.content, end="")
        elif chunk.type == "thinking":
            print(f"[思考] {chunk.content}", end="")
        elif chunk.type == "tool_call":
            print(f"\n>> 调用工具: {chunk.tool_name}({chunk.args})")
        elif chunk.type == "done":
            print(f"\n完成 (tokens: {chunk.usage.total_tokens})")
```

**取消流式执行（v1.10.3+）：**

通过 `cancel_event` 参数传入 `asyncio.Event`，在任意时刻调用 `event.set()` 即可取消正在进行的流：

```python
import asyncio

cancel = asyncio.Event()

async for chunk in client.stream("写一篇长文章", cancel_event=cancel):
    if chunk.type == "text_delta":
        print(chunk.content, end="")
        # 收到足够内容后取消
        if some_condition:
            cancel.set()
    elif chunk.type == "cancelled":
        print("\n[已取消]")
        break
```

取消后 core 层会 yield `CancelledEvent`，SDK 转为 `StreamChunk(type="cancelled")`。如果使用了 `session_id`，session 中会保存 `"(cancelled)"` 占位消息，保持会话一致性。

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
# 自动会话（v1.7.1+，推荐）— run() 自动创建 session
r1 = await client.run("创建 Flask 应用")
sid = r1.session_id  # 自动生成的 session_id

# 后续轮次使用同一 session_id 即可保持上下文
r2 = await client.run("添加 /health 端点", session_id=sid)
r3 = await client.run("添加用户认证", session_id=sid)

# 也可以手动创建会话（可自定义标题）
session = await client.create_session(
    title="My Project",
    model="claude-sonnet-4-0",
    workdir="/path/to/project",
)
r4 = await client.run("分析项目结构", session_id=session.id)

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

#### 5. 健康检查

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
        # 第一轮：自动创建 session
        r1 = await client.run("创建一个 Flask 应用")
        print(r1.output)
        sid = r1.session_id  # 拿到自动生成的 session_id

        # 第二轮：传入 session_id 保持上下文
        r2 = await client.run("添加一个 /health 端点", session_id=sid)
        print(r2.output)

        # 第三轮
        r3 = await client.run("添加 JWT 用户认证", session_id=sid)
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
                    print("\n完成")
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

## 多模态 Prompt

> v1.5.0 新增

SDK 的 `run()` 和 `stream()` 方法支持多模态 Prompt，可以同时发送文本和图片。Prompt 类型定义为 `Union[str, MultimodalPrompt]`——传入纯字符串是最常见的用法，当需要附带图片时使用 `MultimodalPrompt`。

```python
import asyncio
import base64
from cody import AsyncCodyClient
from cody.core.prompt import MultimodalPrompt, ImageData

async def main():
    async with AsyncCodyClient() as client:
        # 纯文本 Prompt（最常见）
        result = await client.run("创建一个 Flask 应用")

        # 多模态 Prompt：文本 + 图片
        with open("screenshot.png", "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        prompt = MultimodalPrompt(
            text="根据这个 UI 截图，用 HTML + CSS 实现这个页面",
            images=[
                ImageData(
                    data=image_b64,
                    media_type="image/png",
                    filename="screenshot.png",
                )
            ],
        )
        result = await client.run(prompt)
        print(result.output)

asyncio.run(main())
```

**支持的图片格式：**
- `image/png`
- `image/jpeg`
- `image/webp`
- `image/gif`

**多张图片：**
```python
prompt = MultimodalPrompt(
    text="对比这两张截图，指出 UI 差异",
    images=[
        ImageData(data=before_b64, media_type="image/png", filename="before.png"),
        ImageData(data=after_b64, media_type="image/png", filename="after.png"),
    ],
)
result = await client.run(prompt)
```

**流式输出同样支持多模态：**
```python
async for chunk in client.stream(prompt):
    if chunk.type == "text_delta":
        print(chunk.content, end="", flush=True)
```

---

## 思考模式

思考模式（Thinking Mode）让模型在回答前先进行内部推理，适用于复杂任务（架构设计、bug 分析、代码重构等）。启用后，流式输出会额外产生 `thinking` 类型的 chunk。

### 通过 Builder 配置

```python
from cody.sdk import Cody

client = (
    Cody()
    .workdir("/path/to/project")
    .thinking(True, budget=10000)  # 启用思考，预算 10000 tokens
    .build()
)

async with client:
    result = await client.run("分析这个项目的架构问题，给出重构方案")
    if result.thinking:
        print(f"思考过程: {result.thinking}")
    print(result.output)
```

### 通过 Config 配置

```python
from cody.sdk import AsyncCodyClient, config

cfg = config(
    model="claude-sonnet-4-0",
    enable_thinking=True,
    thinking_budget=8000,
)
async with AsyncCodyClient(config=cfg) as client:
    result = await client.run("这段代码有什么潜在的并发问题？")
    print(result.output)
```

### 通过 SDKConfig 配置

```python
from cody.sdk import SDKConfig, ModelConfig, AsyncCodyClient

cfg = SDKConfig(
    workdir="/path/to/project",
    model=ModelConfig(
        model="claude-sonnet-4-0",
        enable_thinking=True,
        thinking_budget=10000,
    ),
)
async with AsyncCodyClient(config=cfg) as client:
    result = await client.run("重构这个模块")
    print(result.output)
```

### 流式获取思考过程

```python
async for chunk in client.stream("设计一个分布式任务调度系统"):
    if chunk.type == "thinking":
        print(f"[思考] {chunk.content}", end="")
    elif chunk.type == "text_delta":
        print(chunk.content, end="")
    elif chunk.type == "done":
        print("\n完成")
```

### 事件钩子监听思考

```python
from cody.sdk import Cody, EventType

client = Cody().workdir(".").thinking(True).enable_events().build()

client.on(EventType.THINKING_START, lambda e: print("开始思考..."))
client.on(EventType.THINKING_CHUNK, lambda e: print(f"  {e.content}", end=""))
client.on(EventType.THINKING_END, lambda e: print("\n思考完毕"))
```

---

## 多工作目录与 allowed_roots

> v1.2.0 新增

默认情况下，Cody Agent 的文件操作仅限于 `workdir` 目录。通过 `allowed_roots` 可以授权 Agent 访问多个目录，适用于 monorepo、跨项目引用等场景。

### 通过 Builder 配置

```python
from cody.sdk import Cody

# 方式 1：逐个添加
client = (
    Cody()
    .workdir("/workspace/frontend")
    .allowed_root("/workspace/frontend")
    .allowed_root("/workspace/shared-libs")
    .allowed_root("/workspace/proto")
    .build()
)

# 方式 2：批量设置
client = (
    Cody()
    .workdir("/workspace/frontend")
    .allowed_roots([
        "/workspace/frontend",
        "/workspace/shared-libs",
        "/workspace/proto",
    ])
    .build()
)
```

### 通过 Config 配置

```python
from cody.sdk import config, AsyncCodyClient

cfg = config(
    workdir="/workspace/frontend",
    allowed_roots=[
        "/workspace/frontend",
        "/workspace/shared-libs",
        "/workspace/proto",
    ],
)
async with AsyncCodyClient(config=cfg) as client:
    # Agent 可以读写上述三个目录下的文件
    result = await client.run("把 shared-libs 中的 utils 模块引入到前端项目")
    print(result.output)
```

### 通过 SDKConfig 配置

```python
from cody.sdk import SDKConfig, SecurityConfig, AsyncCodyClient

cfg = SDKConfig(
    workdir="/workspace/frontend",
    security=SecurityConfig(
        allowed_roots=[
            "/workspace/frontend",
            "/workspace/shared-libs",
        ],
        # 自定义命令黑名单（框架内置 rm -rf /、dd if=、:(){）
        blocked_commands=[
            "rm -rf", "git push --force",
            "chmod -R 777", "| bash", "| sh",
        ],
    ),
)
async with AsyncCodyClient(config=cfg) as client:
    result = await client.run("跨项目重构")
    print(result.output)
```

### 典型场景

```python
# Monorepo：主项目 + 共享库
client = (
    Cody()
    .workdir("/repo/packages/app")
    .allowed_roots([
        "/repo/packages/app",
        "/repo/packages/shared",
        "/repo/packages/ui-components",
    ])
    .build()
)

# 前后端联调
client = (
    Cody()
    .workdir("/projects/backend")
    .allowed_roots([
        "/projects/backend",
        "/projects/frontend/src",
    ])
    .build()
)
```

### 严格读边界（v1.9.2+）

默认情况下，读操作（`read_file`、`grep`、`glob` 等）可以访问 `workdir` 和 `allowed_roots` 之外的路径，仅写操作受限。开启 `strict_read_boundary` 后，读操作也被限制在边界内：

```python
# Builder 方式
client = (
    Cody()
    .workdir("/workspace/project")
    .allowed_root("/workspace/shared")
    .strict_read_boundary()
    .build()
)

# Config 方式
cfg = config(
    workdir="/workspace/project",
    allowed_roots=["/workspace/shared"],
    strict_read_boundary=True,
)
```

当 Agent 尝试读取边界外的文件时，会收到明确的拒绝信息（包含可访问的目录列表），模型会自动调整路径重试。

---

## 技能管理

Cody 支持 Agent Skills 开放标准（agentskills.io），技能以 `SKILL.md` 文件形式定义，按四层优先级加载：自定义（`custom_dirs`） > 项目级（`.cody/skills/`） > 全局（`~/.cody/skills/`） > 内置。

SDK 提供 `list_skills()` 和 `get_skill()` 方法查询技能，也可以通过 `SkillManager` 进行启用/禁用操作。

### 查询技能

```python
import asyncio
from cody import AsyncCodyClient

async def main():
    async with AsyncCodyClient(workdir="/path/to/project") as client:
        # 列出所有技能
        skills = await client.list_skills()
        for skill in skills:
            status = "已启用" if skill["enabled"] else "已禁用"
            print(f"  {skill['name']}: {skill['description']} [{status}] ({skill['source']})")

        # 获取技能详情（含完整文档）
        skill = await client.get_skill("git")
        print(f"\n=== {skill['name']} ===")
        print(f"来源: {skill['source']}")
        print(f"状态: {'已启用' if skill['enabled'] else '已禁用'}")
        print(f"文档:\n{skill['documentation']}")

asyncio.run(main())
```

### 启用/禁用技能

SDK 客户端通过 `SkillManager` 管理技能的启用状态：

```python
import asyncio
from cody.core.config import Config
from cody.core.skill_manager import SkillManager
from pathlib import Path

async def main():
    workdir = Path("/path/to/project")
    cfg = Config.load(workdir=workdir)
    sm = SkillManager(config=cfg, workdir=workdir)

    # 列出所有技能
    for skill in sm.list_skills():
        print(f"{skill.name}: enabled={skill.enabled}")

    # 启用技能
    sm.enable_skill("github")
    print("github 已启用")

    # 禁用技能
    sm.disable_skill("docker")
    print("docker 已禁用")

    # 获取技能的系统提示注入 XML
    prompt_xml = sm.to_prompt_xml()
    print(prompt_xml)

asyncio.run(main())
```

### 在 Builder 中配合技能使用

技能在 Agent 运行时自动注入系统提示，无需额外配置。只需确保项目目录下有 `.cody/skills/` 或全局 `~/.cody/skills/` 中有对应的 `SKILL.md` 文件：

```python
from cody.sdk import Cody

# 技能会自动从 workdir/.cody/skills/ 加载
client = (
    Cody()
    .workdir("/path/to/project")  # 项目目录下有 .cody/skills/git/SKILL.md
    .build()
)

async with client:
    # Agent 会自动识别并使用已启用的技能
    result = await client.run("用 git 提交当前更改")
    print(result.output)
```

### 验证技能

```python
from cody.core.config import Config
from cody.core.skill_manager import SkillManager
from pathlib import Path

workdir = Path("/path/to/project")
cfg = Config.load(workdir=workdir)
sm = SkillManager(config=cfg, workdir=workdir)

# 验证技能目录是否符合 Agent Skills 规范
skill_dir = Path("/path/to/project/.cody/skills/my-skill")
problems = sm.validate_skill(skill_dir)
if problems:
    print("验证失败:")
    for p in problems:
        print(f"  - {p}")
else:
    print("验证通过")
```

### 自定义 Skill 目录

SDK 支持配置自定义 Skill 搜索目录，自定义目录优先级最高（在项目级之前）：

```python
# Builder 方式
client = (
    Cody()
    .workdir("/my/project")
    .model("claude-sonnet-4-0")
    .skill_dir("/shared/team-skills")
    .skill_dir("/home/user/my-skills")
    .build()
)

# config() 便捷函数
cfg = config(
    model="claude-sonnet-4-0",
    workdir="/my/project",
    skill_dirs=["/shared/team-skills", "/home/user/my-skills"],
)
client = AsyncCodyClient(config=cfg)
```

也可以通过 JSON 配置文件或环境变量设置：

```json
// .cody/config.json
{
  "skills": {
    "custom_dirs": ["/shared/team-skills"]
  }
}
```

```bash
# 环境变量（冒号分隔）
export CODY_SKILL_DIRS=/shared/team-skills:/home/user/my-skills
```

**优先级顺序：** custom > project（`.cody/skills/`） > global（`~/.cody/skills/`） > builtin

---

## 事件系统

```python
from cody.sdk import Cody, EventType

# 方式 1：Builder 链式注册（推荐，自动启用 events）
client = (
    Cody()
    .workdir(".")
    .on("tool_call", lambda e: print(f"Tool: {e.tool_name}({list(e.args.keys())})"))
    .on("tool_result", lambda e: print(f"Result: {e.tool_name} -> {e.result[:60]}"))
    .build()
)

# 方式 2：构造后注册（需手动 enable_events）
client = Cody().workdir(".").enable_events().build()
client.on(EventType.TOOL_CALL, lambda e: print(f"Tool: {e.tool_name}"))
client.on("run_end", lambda e: print(f"Done: {e.result[:50]}"))  # 也接受字符串

async with client:
    await client.run("Read README.md")
```

> **v1.7.1 变更**：`on()` 可以在 Builder 上链式调用，event_type 支持字符串（如 `"tool_call"`）和 `EventType` 枚举。

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

## MCP 集成

> v1.9.0 新增

SDK 支持通过 MCP（Model Context Protocol）连接外部工具服务器，支持 stdio（子进程）和 HTTP（远程端点）两种传输方式。

### 通过 Builder 配置

```python
from cody.sdk import Cody

client = (
    Cody()
    .workdir("/path/to/project")
    # stdio 传输（本地子进程）
    .mcp_stdio_server(
        "github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": "ghp_xxx"},
    )
    # HTTP 传输（远程端点）
    .mcp_http_server(
        "feishu",
        url="https://mcp.feishu.cn/mcp",
        headers={"X-Lark-MCP-UAT": "your-token"},
    )
    .auto_start_mcp(True)  # 首次 run() 自动启动（默认 False）
    .build()
)

async with client:
    # auto_start_mcp=True 时，MCP 服务器在首次 run() 时自动启动
    result = await client.run("总结飞书文档")
    print(result.output)
```

### 手动启动

```python
client = (
    Cody()
    .mcp_http_server("feishu", url="https://mcp.feishu.cn/mcp", headers={...})
    .build()  # auto_start_mcp 默认 False
)

async with client:
    await client.start_mcp()  # 手动启动，控制启动时机
    result = await client.run("总结飞书文档")
```

### 动态添加 MCP 服务器

运行中可随时添加新的 MCP 服务器，添加后立即可用：

```python
async with client:
    # 运行中动态添加
    await client.add_mcp_server(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": "ghp_xxx"},
    )

    # HTTP 方式动态添加
    await client.add_mcp_server(
        name="feishu",
        transport="http",
        url="https://mcp.feishu.cn/mcp",
        headers={"X-Lark-MCP-UAT": "your-token"},
    )

    # 立刻就能用
    result = await client.run("list my GitHub PRs")
```

### 直接调用 MCP 工具

```python
# 列出所有 MCP 工具
tools = await client.mcp_list_tools()
print(tools)

# 直接调用 MCP 工具
result = await client.mcp_call("feishu/fetch-doc", {"url": "https://..."})
print(result)
```

### 通过 SDKConfig 配置

```python
from cody.sdk import SDKConfig, MCPConfig, MCPServerConfig, AsyncCodyClient

cfg = SDKConfig(
    workdir="/path/to/project",
    mcp=MCPConfig(servers=[
        MCPServerConfig(
            name="feishu",
            transport="http",
            url="https://mcp.feishu.cn/mcp",
            headers={"X-Lark-MCP-UAT": "your-token"},
        ),
        MCPServerConfig(
            name="github",
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
        ),
    ]),
)
async with AsyncCodyClient(config=cfg, auto_start_mcp=True) as client:
    result = await client.run("task")
```

---

## 人工交互（Human-in-the-Loop Interaction）

当 AI 需要人类确认或回答时，可以通过交互机制暂停执行、等待响应。支持两种场景：

- **`question` 工具**：AI 主动提问，等待人类回答
- **CONFIRM 级别工具审批**：`exec_command`、`write_file`、`edit_file` 等变更性工具在执行前暂停，等待人类批准或拒绝

### 配置

```python
# 开启交互，30s 超时（默认）
client = Cody().interaction(enabled=True, timeout=30).build()

# 自定义超时
client = Cody().interaction(enabled=True, timeout=60).build()
```

### 行为

| 模式 | `interaction.enabled=False`（默认） | `interaction.enabled=True` |
|------|-------------------------------------|----------------------------|
| `run()` / `stream()` | 自动批准，AI 全自主 | 暂停等待人类响应 |
| `run_sync()` | 自动批准 | **忽略配置，仍然自动批准**（同步无法并发等待） |

> **注意**：当 `interaction.enabled=False` 时，CONFIRM 级别工具（如 `exec_command`）也会自动放行。如需审批变更操作，必须开启 interaction。

### 使用示例

```python
import asyncio
from cody.sdk import Cody
from cody.core.errors import InteractionTimeoutError

client = Cody().interaction(enabled=True, timeout=30).build()

async def main():
    try:
        async for chunk in client.stream("帮我重构这个文件"):
            if chunk.type == "interaction_request":
                # AI 在等你回答
                print(f"AI asks: {chunk.content}")
                print(f"Options: {chunk.options}")
                # 30s 内必须响应
                await client.submit_interaction(
                    request_id=chunk.request_id,
                    action="answer",
                    content="Yes, go ahead",
                )
            elif chunk.type == "text_delta":
                print(chunk.content, end="")
    except InteractionTimeoutError as e:
        print(f"交互超时: {e}")
```

### 超时行为

超时后直接抛出 `InteractionTimeoutError`，终止 stream 迭代。调用方通过 `try/except` 捕获。`run()` 同理。

---

## 熔断器（Circuit Breaker）

AgentRunner 内置熔断保护，防止 Agent 失控消耗过多资源。熔断器在每次 `run()` / `run_stream()` / `run_sync()` 执行前自动重置，执行后检查。

### 触发条件

| 条件 | 默认阈值 | 配置项 |
|------|---------|--------|
| Token 超限 | 200,000 | `circuit_breaker.max_tokens` |
| 成本超限 | $5.00 | `circuit_breaker.max_cost_usd` |
| 步数超限 | 0（无限制） | `circuit_breaker.max_steps` |
| 死循环检测 | 连续 6 次相似结果 | `circuit_breaker.loop_detect_turns` + `loop_similarity_threshold` |

### 行为

- `run()` / `run_sync()`：抛出 `CircuitBreakerError`
- `run_stream()`：yield `CircuitBreakerEvent`（SDK 转为 `StreamChunk(type="circuit_breaker")`）
- 带 session 时：自动写入 `"(circuit breaker: {reason})"` 消息保持会话一致

### 配置

配置优先级：**SDK 代码 > 项目配置 > 全局配置**

```python
# 方式 1：Builder 关键字参数
client = (
    Cody()
    .circuit_breaker(max_cost_usd=10.0, max_tokens=500_000, max_steps=50)
    .build()
)

# 方式 2：Builder + CircuitBreakerConfig 对象
from cody.sdk import CircuitBreakerConfig

cb = CircuitBreakerConfig(
    max_cost_usd=10.0,
    max_tokens=500_000,
    max_steps=50,
    model_prices={"claude-sonnet-4-0": 0.000009},
)
client = Cody().circuit_breaker(cb).build()

# 方式 3：配置文件 .cody/config.json
{
    "circuit_breaker": {
        "enabled": true,
        "max_tokens": 200000,
        "max_cost_usd": 5.0,
        "max_steps": 0,
        "loop_detect_turns": 6,
        "loop_similarity_threshold": 0.9
    }
}
```

### 捕获熔断

```python
from cody.core.errors import CircuitBreakerError

try:
    result = await client.run("一个可能很耗资源的任务")
except CircuitBreakerError as e:
    print(f"熔断: {e.reason}, tokens={e.tokens_used}, cost=${e.cost_usd:.4f}")

# 流式场景
async for chunk in client.stream("任务"):
    if chunk.type == "circuit_breaker":
        print(f"熔断: {chunk.content}")
        break
    elif chunk.type == "text_delta":
        print(chunk.content, end="")
```

---

## 结构化输出（Structured Output）

`CodyResult`（core 层）现在包含 `metadata: TaskMetadata` 字段，自动从模型输出中提取结构化信息。

### TaskMetadata

```python
@dataclass
class TaskMetadata:
    summary: str                    # 首行摘要（最多 200 字符）
    confidence: Optional[float]     # AI 自评置信度（0.0-1.0），解析 <confidence> 标记
    issues: list[str]               # 已知问题
    next_steps: list[str]           # 建议的后续步骤
```

### 使用

```python
# 通过 core 层直接使用
runner = client.get_runner()
result = await runner.run("修复登录 bug")
if result.metadata:
    print(f"摘要: {result.metadata.summary}")
    if result.metadata.confidence is not None:
        print(f"置信度: {result.metadata.confidence:.0%}")
```

### 置信度标记

模型输出中包含 `<confidence>0.85</confidence>` 标记时，会自动解析为 `metadata.confidence`。值必须在 0.0-1.0 范围内，否则忽略。

---

## 人工交互（Human Interaction）

统一的人工交互层，支持三种场景：
- **question**：AI 向用户提问
- **confirm**：工具执行前的确认
- **feedback**：请求结构化反馈（批准/拒绝/修订）

### 流式监听

```python
async for chunk in client.stream("重构这个模块"):
    if chunk.type == "interaction_request":
        print(f"[{chunk.interaction_kind}] {chunk.content}")
        print(f"选项: {chunk.options}")
        # 提交响应
        await client.submit_interaction(
            request_id=chunk.request_id,
            action="approve",       # "approve" / "reject" / "revise" / "answer"
            content="",             # 修订内容或回答
        )
    elif chunk.type == "text_delta":
        print(chunk.content, end="")
```

### InteractionRequest / InteractionResponse

```python
from cody.core.interaction import InteractionRequest, InteractionResponse

# 请求（由 runner 创建）
req = InteractionRequest(
    kind="confirm",
    prompt="是否删除 old_module.py？",
    options=["确认删除", "保留"],
)

# 响应（由消费者提交）
resp = InteractionResponse(
    request_id=req.id,
    action="approve",
)
await client.submit_interaction(req.id, action="approve")
```

---

## 项目记忆（Project Memory）

跨会话的项目记忆系统，自动积累 AI 在项目上的经验。每个项目（按 workdir 标识）独立存储，分四个类别：

| 类别 | 说明 | 示例 |
|------|------|------|
| `conventions` | 代码风格、命名规范 | "使用 ruff 格式化，行宽 100" |
| `patterns` | 设计模式、常用工具 | "使用 Factory 模式创建 handler" |
| `issues` | 已知 bug、陷阱 | "SQLite 在并发写入时需要 WAL 模式" |
| `decisions` | 架构选择、技术决策 | "选择 FastAPI 而非 Flask" |

### 写入记忆

```python
await client.add_memory(
    category="conventions",
    content="项目使用 ruff 管理 lint，行宽 100",
    confidence=0.9,
    tags=["lint", "style"],
)

await client.add_memory(
    category="decisions",
    content="选择 pydantic-ai 作为 Agent 框架",
    source_task_id="task_001",
    source_task_title="评估 Agent 框架",
)
```

### 读取记忆

```python
memory = await client.get_memory()
for category, entries in memory.items():
    print(f"\n=== {category} ===")
    for entry in entries:
        print(f"  [{entry['confidence']:.0%}] {entry['content']}")
```

### 清除记忆

```python
await client.clear_memory()
```

### 工作原理

- 记忆存储在 `~/.cody/memory/<project_hash>/` 目录下，每个类别一个 JSON 文件
- `AgentRunner` 初始化时自动加载记忆，注入到 system prompt 的 "Project Memory" 段
- 每个类别最多 50 条，超出时自动淘汰最旧的条目
- 低置信度条目（< 0.3）不会注入 system prompt

---

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
# 多轮对话：首次调用自动创建 session
r = await client.run("创建项目")
await client.run("添加功能", session_id=r.session_id)
await client.run("修复 bug", session_id=r.session_id)
```

### 4. 并发请求

```python
# Python asyncio 并发
async with asyncio.TaskGroup() as tg:
    task1 = tg.create_task(client.run("任务 1"))
    task2 = tg.create_task(client.run("任务 2"))
```

### 5. 多模态 + 思考模式组合

```python
from cody.sdk import Cody
from cody.core.prompt import MultimodalPrompt, ImageData

client = Cody().workdir(".").thinking(True, budget=10000).build()

async with client:
    prompt = MultimodalPrompt(
        text="分析这个架构图，找出潜在的性能瓶颈",
        images=[ImageData(data=arch_diagram_b64, media_type="image/png")],
    )
    result = await client.run(prompt)
    print(result.output)
```

---

## API 参考

### 客户端

| 类/函数 | 说明 |
|--------|------|
| `AsyncCodyClient` | 异步客户端（推荐） |
| `CodyClient` | 同步客户端 |
| `Cody()` | Builder 工厂函数，返回 `CodyBuilder` |
| `config()` | 便捷配置工厂函数，返回 `SDKConfig` |

### Builder 方法（`CodyBuilder`）

| 方法 | 说明 |
|------|------|
| `.workdir(path)` | 设置工作目录 |
| `.model(name)` | 设置模型名 |
| `.api_key(key)` | 设置 API Key |
| `.base_url(url)` | 设置自定义 API 地址 |
| `.thinking(enabled, budget=)` | 启用思考模式 |
| `.permission(tool, level)` | 设置工具权限 |
| `.allowed_root(path)` / `.allowed_roots(paths)` | 设置允许的文件访问路径 |
| `.strict_read_boundary(enabled=True)` | 限制读操作也遵守访问边界（v1.9.2+） |
| `.skill_dir(path)` / `.skill_dirs(paths)` | 添加自定义 Skill 搜索目录 |
| `.db_path(path)` | 设置会话数据库路径 |
| `.enable_metrics()` | 启用指标收集 |
| `.enable_events()` | 启用事件系统 |
| `.tool(func)` | 注册自定义工具函数（`async def f(ctx, ...) -> str`） |
| `.system_prompt(text)` | 替换默认 persona（CODY.md/记忆/Skills 仍保留） |
| `.extra_system_prompt(text)` | 在所有内置 prompt 后追加自定义指令 |
| `.on(event_type, handler)` | 注册事件处理器（自动启用 events） |
| `.mcp_server(config)` | 添加 MCP 服务器配置（dict 或 MCPServerConfig） |
| `.mcp_stdio_server(name, command, args=, env=)` | 添加 stdio MCP 服务器（v1.9.0+） |
| `.mcp_http_server(name, url, headers=)` | 添加 HTTP MCP 服务器（v1.9.0+） |
| `.auto_start_mcp(enabled)` | 首次 run() 自动启动 MCP（默认 False，v1.9.0+） |
| `.interaction(enabled=True, timeout=30)` | 配置人工交互（仅异步模式生效） |
| `.circuit_breaker(config_or_kwargs)` | 配置熔断器（支持 `CircuitBreakerConfig` 对象或关键字参数） |
| `.lsp_languages(languages)` | 设置 LSP 语言列表 |
| `.build()` | 构建并返回 `AsyncCodyClient` |

### 核心方法

| 方法 | 说明 |
|------|------|
| `client.run(prompt, session_id=, include_tools=, exclude_tools=)` | 执行任务，返回 `RunResult`。`include_tools` / `exclude_tools` 控制本次可用工具 |
| `client.stream(prompt, session_id=, cancel_event=, include_tools=, exclude_tools=)` | 流式执行，yield `StreamChunk`（`cancel_event` v1.10.3+） |
| `client.run_stream(prompt, session_id=, cancel_event=)` | `stream()` 的别名 |
| `client.tool(name, params)` | 直接调用内置工具，返回 `ToolResult` |

### 熔断 / 交互 / 记忆方法

| 方法 | 说明 |
|------|------|
| `client.submit_interaction(request_id, action=, content=)` | 提交人工交互响应 |
| `client.add_memory(category, content, ...)` | 添加项目记忆条目 |
| `client.get_memory()` | 获取所有项目记忆（按类别分组） |
| `client.clear_memory()` | 清除项目所有记忆 |

### MCP 方法（v1.9.0+）

| 方法 | 说明 |
|------|------|
| `client.start_mcp()` | 手动启动已配置的 MCP 服务器（`auto_start_mcp=True` 时自动调用） |
| `client.add_mcp_server(name, ...)` | 运行时动态添加并立即启动 MCP 服务器 |
| `client.mcp_list_tools()` | 列出所有已连接 MCP 服务器的工具 |
| `client.mcp_call(tool_name, args)` | 直接调用 MCP 工具（格式：`"server/tool"`） |

### 会话方法

| 方法 | 说明 |
|------|------|
| `client.create_session(title=)` | 创建会话 |
| `client.list_sessions(limit=)` | 列出会话 |
| `client.get_session(session_id)` | 获取会话详情 |
| `client.delete_session(session_id)` | 删除会话 |
| `client.get_latest_session(workdir=)` | 获取最近的会话（v1.7.4+） |
| `client.get_message_count(session_id)` | 获取会话消息数（v1.7.4+） |
| `client.add_message(session_id, role, content)` | 添加消息到会话（v1.7.4+） |
| `client.update_title(session_id, title)` | 更新会话标题（v1.7.4+） |
| `AsyncCodyClient.messages_to_history(messages)` | 将消息列表转换为对话历史（静态方法，v1.7.4+） |

### 技能方法

| 方法 | 说明 |
|------|------|
| `client.list_skills()` | 列出所有技能 |
| `client.get_skill(name)` | 获取技能详情和文档 |

### 高级方法（Power-user API）

| 方法 | 说明 |
|------|------|
| `client.set_config(config)` | 注入预构建的 core Config（含 thinking、extra_roots 等覆盖），重置 runner（v1.7.4+） |
| `client.get_runner()` | 获取底层 AgentRunner，用于原始流式事件或 MCP 控制（v1.7.4+） |
| `client.get_session_store()` | 获取底层 SessionStore，用于同步会话操作（v1.7.4+） |

### 其他方法

| 方法 | 说明 |
|------|------|
| `client.health()` | 健康检查 |
| `client.on(event_type, handler)` | 注册事件处理器 |
| `client.on_async(event_type, handler)` | 注册异步事件处理器 |
| `client.get_metrics()` | 获取指标摘要 |
| `client.close()` | 释放资源 |

### 便捷方法

| 方法 | 说明 |
|------|------|
| `client.read_file(path)` | 读取文件 |
| `client.write_file(path, content)` | 写入文件 |
| `client.edit_file(path, old, new)` | 编辑文件 |
| `client.list_directory(path)` | 列出目录 |
| `client.grep(pattern, include=)` | 搜索内容 |
| `client.glob(pattern)` | 查找文件 |
| `client.exec_command(command)` | 执行命令 |
| `client.search_files(query)` | 模糊搜索文件 |
| `client.lsp_diagnostics(file)` | LSP 诊断 |
| `client.lsp_definition(file, line, col)` | 跳转定义 |
| `client.lsp_references(file, line, col)` | 查找引用 |
| `client.lsp_hover(file, line, col)` | 悬停信息 |

### 配置类

| 类 | 说明 |
|------|------|
| `SDKConfig` | 完整 SDK 配置 |
| `ModelConfig` | 模型配置（模型名、API Key、思考模式等） |
| `PermissionConfig` | 工具权限配置 |
| `SecurityConfig` | 安全配置（`allowed_roots`、`blocked_commands`、`strict_read_boundary` 等） |
| `MCPConfig` | MCP 服务器配置 |
| `MCPServerConfig` | 单个 MCP 服务器配置（v1.9.0+，支持 stdio/http 传输） |
| `LSPConfig` | LSP 语言配置 |

### 响应类型

| 类 | 说明 |
|------|------|
| `RunResult` | 执行结果（output, session_id, usage, thinking） |
| `StreamChunk` | 流式块（type, content, session_id, tool_name, args, tool_call_id, usage, request_id, interaction_kind, options） |
| `ToolResult` | 工具结果（result） |
| `SessionInfo` | 会话摘要 |
| `SessionDetail` | 会话详情（含消息列表） |
| `Usage` | Token 用量（input_tokens, output_tokens, total_tokens） |

### Prompt 类型

| 类 | 说明 |
|------|------|
| `Prompt` | `Union[str, MultimodalPrompt]`，统一 Prompt 类型 |
| `MultimodalPrompt` | 多模态 Prompt（text + images） |
| `ImageData` | 图片数据（base64 编码 + media_type） |

### Core 类型（通过 `cody.core` 访问）

| 类 | 说明 |
|------|------|
| `TaskMetadata` | 结构化输出元数据（summary, confidence, issues, next_steps） |
| `CircuitBreakerConfig` | 熔断器配置（max_tokens, max_cost_usd, loop_detect_turns 等） |
| `CircuitBreakerError` | 熔断异常（reason, tokens_used, cost_usd） |
| `InteractionRequest` | 人工交互请求（id, kind, prompt, options, context） |
| `InteractionResponse` | 人工交互响应（request_id, action, content） |
| `ProjectMemoryStore` | 项目记忆存储（from_workdir, add_entries, get_all_entries 等） |
| `MemoryEntry` | 记忆条目（content, confidence, tags, source_task_id 等） |

### 错误类型

| 错误 | HTTP 状态码 | 说明 |
|------|------------|------|
| `CodyError` | — | 基础错误 |
| `CodyModelError` | 500 | 模型 API 调用失败 |
| `CodyToolError` | 500 | 工具执行失败 |
| `CodyPermissionError` | 403 | 权限不足 |
| `CodyNotFoundError` | 404 | 资源不存在 |
| `CodyRateLimitError` | 429 | 速率限制 |
| `CodyConfigError` | 400 | 配置错误 |
| `CodyTimeoutError` | 408 | 超时 |
| `CodyConnectionError` | 503 | 连接失败 |
| `CodySessionError` | 400 | 会话错误 |

---

**最后更新:** 2026-03-20
