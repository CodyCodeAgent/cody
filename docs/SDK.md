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
10. [便捷方法](#便捷方法)
11. [错误处理](#错误处理)
12. [最佳实践](#最佳实践)
13. [API 参考](#api-参考)

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
```

**流式事件类型：**

| 类型 | 说明 | 特有字段 |
| ---- | ---- | -------- |
| `text_delta` | 文本内容（增量） | `content` |
| `thinking` | 思考内容（增量） | `content` |
| `tool_call` | 工具调用 | `tool_name`, `args`, `tool_call_id` |
| `tool_result` | 工具结果 | `content`（结果文本）, `tool_name`, `tool_call_id` |
| `done` | 任务完成 | `usage`（Token 用量） |
| `compact` | 上下文压缩 | — |

**完整示例：**
```python
async with AsyncCodyClient() as client:
    async for chunk in client.run_stream("创建 Flask 应用"):
        if chunk.type == "text_delta":
            print(chunk.content, end="")
        elif chunk.type == "thinking":
            print(f"[思考] {chunk.content}", end="")
        elif chunk.type == "tool_call":
            print(f"\n>> 调用工具: {chunk.tool_name}({chunk.args})")
        elif chunk.type == "done":
            print(f"\n完成 (tokens: {chunk.usage.total_tokens})")
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

---

## 技能管理

Cody 支持 Agent Skills 开放标准（agentskills.io），技能以 `SKILL.md` 文件形式定义，按三层优先级加载：项目级（`.cody/skills/`） > 全局（`~/.cody/skills/`） > 内置。

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

### 核心方法

| 方法 | 说明 |
|------|------|
| `client.run(prompt, session_id=)` | 执行任务，返回 `RunResult` |
| `client.stream(prompt, session_id=)` | 流式执行，yield `StreamChunk` |
| `client.run_stream(prompt, session_id=)` | `stream()` 的别名 |
| `client.start_mcp()` | 启动 MCP 服务器（在首次 `stream()` 前调用） |
| `client.tool(name, params)` | 直接调用工具，返回 `ToolResult` |

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
| `SecurityConfig` | 安全配置（`allowed_roots`、`blocked_commands` 等） |
| `MCPConfig` | MCP 服务器配置 |
| `LSPConfig` | LSP 语言配置 |

### 响应类型

| 类 | 说明 |
|------|------|
| `RunResult` | 执行结果（output, session_id, usage, thinking） |
| `StreamChunk` | 流式块（type, content, session_id, tool_name, args, tool_call_id, usage） |
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

**最后更新:** 2026-03-07
