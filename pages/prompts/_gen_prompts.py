"""批量生成 SDK 教程 Prompt 文件（03-13 篇）"""
import os

OUTDIR = os.path.dirname(__file__)

# ── 每篇的核心定义 ──────────────────────────────────────────────────────────

ARTICLES = [
    {
        "n": "03", "file": "03-streaming", "title": "流式输出全解",
        "group": "基础篇", "badge": "blue", "time": "12",
        "prev_file": "02-multi-turn.html", "prev_title": "多轮对话",
        "next_file": "04-tools.html", "next_title": "工具直接调用",
        "desc": "stream()/run_stream() 用法，StreamChunk 12 种类型完整处理，流式取消，思考模式（thinking）",
        "goal": "读者能用 stream() 处理实时输出、识别所有事件类型、实现流式取消、启用思考模式。",
        "content": """
**1. 引言**：为什么需要流式输出——长任务实时反馈，工具调用可见性，用户体验。

**2. 最基础的流式示例**（主示例）：
```python
async for chunk in client.stream("分析整个项目结构"):
    if chunk.type == "text_delta":
        print(chunk.content, end="", flush=True)
    elif chunk.type == "done":
        print(f"\\n完成，共 {chunk.usage.total_tokens} tokens")
```

**3. StreamChunk 字段说明**（参数表）：
type / content / session_id / tool_name / args / tool_call_id / usage / request_id / interaction_kind

**4. 所有 12 种事件类型**（表格 + 说明）：
session_start / text_delta / thinking / tool_call / tool_result / done / cancelled / compact / retry / circuit_breaker / interaction_request / UnknownChunk

**5. 完整处理所有事件的示例**：展示如何在一个 async for 循环里处理所有类型。

**6. 工具调用事件**：重点展示 tool_call + tool_result 的配对处理，让读者看到 AI 在干什么。

**7. 流式取消**（cancel_event）：
```python
cancel = asyncio.Event()
async for chunk in client.stream("写一篇长文章", cancel_event=cancel):
    if chunk.type == "text_delta":
        print(chunk.content, end="")
        if some_condition:
            cancel.set()  # 随时取消
    elif chunk.type == "cancelled":
        print("\\n[已取消]")
        break
```

**8. 思考模式（Thinking）**：
callout-info 说明：部分模型（如 claude-sonnet-4-0）支持思考模式，流里会额外出现 thinking chunk。
```python
client = Cody().workdir(".").thinking(True, budget=10000).build()
async for chunk in client.stream("分析这段代码的性能瓶颈"):
    if chunk.type == "thinking":
        print(f"[思考] {chunk.content}", end="")
    elif chunk.type == "text_delta":
        print(chunk.content, end="")
```

**9. retry 事件处理**：说明 retry 是 API 调用失败自动重试，应清空已缓冲的输出。

**10. stream() 和 run_stream() 的关系**：完全等价，run_stream 是别名。

**11. 小结 + 引向第 04 篇**。
""",
        "sdk_ref": """
```python
# stream() / run_stream() 完全等价
async for chunk in client.stream("任务"):
    ...
async for chunk in client.run_stream("任务"):
    ...

# 参数
async for chunk in client.stream(
    prompt,               # str | MultimodalPrompt
    session_id=None,      # str，可选
    cancel_event=None,    # asyncio.Event，可选（v1.10.3+）
    include_tools=None,   # list[str]，只允许这些工具
    exclude_tools=None,   # list[str]，排除这些工具
):
    ...

# StreamChunk 字段
chunk.type              # str，事件类型
chunk.content           # str，文本内容
chunk.session_id        # str | None
chunk.tool_name         # str | None（tool_call / tool_result 时）
chunk.args              # dict | None（tool_call 时）
chunk.tool_call_id      # str | None
chunk.usage             # Usage | None（done 时）
chunk.request_id        # str | None（interaction_request 时）
chunk.interaction_kind  # str | None（"question"/"confirm"/"feedback"）
chunk.options           # list[str] | None

# 12 种事件类型
# session_start  - 始终是第一个事件，携带 session_id
# text_delta     - 文本增量，content 字段
# thinking       - 思考内容增量（思考模式时）
# tool_call      - 工具调用，tool_name + args + tool_call_id
# tool_result    - 工具结果，content + tool_name + tool_call_id
# done           - 完成，usage 字段
# cancelled      - 取消（cancel_event 触发）
# compact        - 上下文压缩事件
# retry          - 模型调用失败即将重试，attempt/max_attempts/error 字段
# circuit_breaker - 熔断器触发，content 说明原因
# interaction_request - 需要人工输入
# UnknownChunk   - 未知类型

# 思考模式
client = Cody().workdir(".").thinking(True, budget=10000).build()
# thinking chunk: chunk.type == "thinking"
# run() 结果: result.thinking 字段

# 取消
cancel = asyncio.Event()
async for chunk in client.stream("任务", cancel_event=cancel):
    if ...: cancel.set()
    elif chunk.type == "cancelled": break
```"""
    },
    {
        "n": "04", "file": "04-tools", "title": "工具直接调用",
        "group": "工具篇", "badge": "green", "time": "8",
        "prev_file": "03-streaming.html", "prev_title": "流式输出全解",
        "next_file": "05-custom-tools.html", "next_title": "注册自定义工具",
        "desc": "tool() 方法调用 28+ 内置工具，include/exclude_tools 过滤，便捷方法，LSP 工具",
        "goal": "读者能直接调用任意内置工具、过滤工具范围、使用便捷方法快速操作文件和执行命令。",
        "content": """
**1. 引言**：两种工具使用方式——让 AI 自动调用（run/stream）vs 手动直接调用（tool()）。手动调用适合：自动化脚本、测试、精确控制。

**2. tool() 方法基础**（主示例，展示 3-4 个常用工具）：
```python
async with AsyncCodyClient(workdir=".") as client:
    # 读取文件
    result = await client.tool("read_file", {"path": "main.py"})
    print(result.result)

    # 搜索
    result = await client.tool("grep", {"pattern": "def main", "include": "*.py"})
    print(result.result)

    # 执行命令
    result = await client.tool("exec_command", {"command": "python --version"})
    print(result.result)

    # 列出目录
    result = await client.tool("list_directory", {"path": "."})
    print(result.result)
```
说明 `ToolResult.result` 字段（str）。

**3. 28+ 内置工具清单**（表格，分类展示）：
| 分类 | 工具 |
|------|------|
| 文件 I/O | read_file, write_file, edit_file, list_directory |
| 搜索 | grep, glob, search_files, patch |
| 执行 | exec_command |
| Web | webfetch, websearch |
| LSP | lsp_diagnostics, lsp_definition, lsp_references, lsp_hover |
| 文件历史 | undo_file, redo_file, list_file_changes |
| 任务 | todo_write, todo_read |
| 交互 | question |
| 记忆 | save_memory |
| Skills | list_skills, read_skill |
| 子代理 | spawn_agent, get_agent_status, kill_agent |

**4. run/stream 中的工具过滤**：
```python
# 只允许读操作（代码分析场景）
result = await client.run(
    "分析代码质量",
    include_tools=["read_file", "grep", "glob"]
)

# 排除危险操作（只读模式）
async for chunk in client.stream(
    "检查项目结构",
    exclude_tools=["exec_command", "write_file", "edit_file"]
):
    ...
```
callout-tip：include_tools 和 exclude_tools 互斥，不能同时使用。

**5. 便捷方法**（不用 tool()，直接调用）：
```python
content = await client.read_file("main.py")
await client.write_file("hello.py", "print('hello')")
await client.edit_file("main.py", "old text", "new text")
files = await client.glob("**/*.py")
matches = await client.grep("def main", include="*.py")
output = await client.exec_command("ls -la")
```

**6. LSP 工具**（代码智能）：
简要介绍，展示 lsp_diagnostics 示例：
```python
# 获取文件的语法/类型错误
diags = await client.lsp_diagnostics("main.py")
print(diags)

# 跳转到定义
defn = await client.lsp_definition("main.py", line=10, column=5)

# 查找所有引用
refs = await client.lsp_references("main.py", line=10, column=5)
```
callout-info：LSP 需要安装对应语言服务器（Python: pylsp, TS: typescript-language-server, Go: gopls）。

**7. 小结 + 引向第 05 篇**（注册自定义工具）。
""",
        "sdk_ref": """
```python
# tool() 直接调用
result = await client.tool(tool_name: str, params: dict)
result.result  # str，工具输出

# 常用工具及参数
await client.tool("read_file", {"path": "main.py"})
await client.tool("write_file", {"path": "out.py", "content": "..."})
await client.tool("edit_file", {"path": "main.py", "old_str": "...", "new_str": "..."})
await client.tool("list_directory", {"path": "."})
await client.tool("grep", {"pattern": "def main", "include": "*.py", "path": "."})
await client.tool("glob", {"pattern": "**/*.py"})
await client.tool("exec_command", {"command": "ls -la"})
await client.tool("webfetch", {"url": "https://example.com"})

# 工具过滤（run/stream 参数）
await client.run("任务", include_tools=["read_file", "grep"])  # 白名单
await client.run("任务", exclude_tools=["exec_command"])        # 黑名单
# include_tools 和 exclude_tools 互斥

# 便捷方法（直接调用，等价于 tool()）
content = await client.read_file("main.py")
await client.write_file("hello.py", "print('hello')")
await client.edit_file("main.py", "old", "new")
files = await client.glob("**/*.py")
matches = await client.grep("pattern", include="*.py")
output = await client.exec_command("ls -la")
dirs = await client.list_directory(".")
results = await client.search_files("main")

# LSP 便捷方法
diags = await client.lsp_diagnostics("main.py")
defn = await client.lsp_definition("main.py", line=10, column=5)
refs = await client.lsp_references("main.py", line=10, column=5)
hover = await client.lsp_hover("main.py", line=10, column=5)
# LSP 语言服务器：Python(pylsp) / TypeScript(typescript-language-server) / Go(gopls)
```"""
    },
    {
        "n": "05", "file": "05-custom-tools", "title": "注册自定义工具",
        "group": "工具篇", "badge": "green", "time": "10",
        "prev_file": "04-tools.html", "prev_title": "工具直接调用",
        "next_file": "06-prompt.html", "next_title": "Prompt 定制与多模态",
        "desc": "自定义工具函数签名、docstring、Builder .tool() 注册、before_tool/after_tool 中间件",
        "goal": "读者能注册自己的业务函数为 AI 工具，并用中间件拦截/修改工具调用。",
        "content": """
**1. 引言**：自定义工具让 AI 能调用你的业务逻辑——数据库查询、内部 API、特定数据格式处理。

**2. 工具函数签名要求**：
```python
from pydantic_ai import RunContext
from cody.core.deps import CodyDeps

async def my_tool(ctx: RunContext[CodyDeps], param1: str, param2: int = 0) -> str:
    """工具描述——AI 根据这段 docstring 决定何时调用此工具。"""
    return "结果字符串"
```
重点说明三个要求：必须 async、第一个参数必须是 ctx、返回 str、docstring 决定 AI 行为。

**3. 完整示例**（一个实用的自定义工具）：
```python
from pydantic_ai import RunContext
from cody.core.deps import CodyDeps
from cody.sdk import Cody
import httpx

async def fetch_jira_ticket(ctx: RunContext[CodyDeps], ticket_id: str) -> str:
    """从 Jira 获取指定工单的标题、描述和状态。传入工单 ID，如 PROJ-123。"""
    async with httpx.AsyncClient() as c:
        resp = await c.get(
            f"https://your-jira.atlassian.net/rest/api/2/issue/{ticket_id}",
            headers={"Authorization": "Bearer YOUR_TOKEN"}
        )
        data = resp.json()
        return f"[{ticket_id}] {data['fields']['summary']} - {data['fields']['status']['name']}"

client = Cody().workdir(".").tool(fetch_jira_ticket).build()

async with client:
    result = await client.run("查一下 PROJ-456 这个工单说的是什么问题，然后看看代码里有没有相关的 TODO")
    print(result.output)
```

**4. 注册多个工具**：
```python
client = (
    Cody()
    .workdir(".")
    .tool(fetch_jira_ticket)
    .tool(query_database)
    .tool(send_notification)
    .build()
)
```

**5. docstring 的重要性**：callout-warn 说明——docstring 是 AI 决定"何时用这个工具"的唯一依据，必须清晰说明：做什么、接收什么参数、什么时候用。

**6. before_tool 中间件**（工具调用前拦截）：
```python
async def log_and_guard(tool_name: str, args: dict) -> dict | None:
    """返回 dict 继续执行；返回 None 拒绝调用。"""
    print(f"[工具调用] {tool_name}: {args}")
    # 安全检查：禁止删除操作
    if tool_name == "exec_command" and "rm" in args.get("command", ""):
        print("  ✗ 危险命令被拦截")
        return None  # 拒绝
    return args  # 放行

client = Cody().workdir(".").before_tool(log_and_guard).build()
```

**7. after_tool 中间件**（工具返回后处理）：
```python
import os

async def redact_secrets(tool_name: str, args: dict, result: str) -> str:
    """对工具输出脱敏。"""
    secret = os.environ.get("DB_PASSWORD", "")
    if secret and secret in result:
        result = result.replace(secret, "***")
    return result

client = Cody().workdir(".").after_tool(redact_secrets).build()
```

**8. 中间件链**：多个 hook 按注册顺序依次执行。

**9. 小结 + 引向第 06 篇**。
""",
        "sdk_ref": """
```python
# 工具函数签名
from pydantic_ai import RunContext
from cody.core.deps import CodyDeps

async def my_tool(ctx: RunContext[CodyDeps], arg1: str, arg2: int = 0) -> str:
    """描述：AI 根据 docstring 决定何时调用。必须清晰说明功能、参数含义、使用场景。"""
    return "result"

# 注册
client = Cody().workdir(".").tool(my_tool).tool(another_tool).build()

# before_tool hook
# 签名: async (tool_name: str, args: dict) -> dict | None
# 返回 dict → 继续执行（可修改 args）
# 返回 None → 拒绝调用（触发 ModelRetry，模型自我纠正）
async def before(tool_name: str, args: dict) -> dict | None:
    print(f"调用 {tool_name}")
    return args

client = Cody().workdir(".").before_tool(before).build()

# after_tool hook
# 签名: async (tool_name: str, args: dict, result: str) -> str
async def after(tool_name: str, args: dict, result: str) -> str:
    return result.replace("secret", "***")

client = Cody().workdir(".").after_tool(after).build()

# 多个 hook 链式执行
client = (
    Cody()
    .before_tool(log_tool)
    .before_tool(security_check)   # 按注册顺序执行
    .after_tool(redact_output)
    .build()
)
```"""
    },
    {
        "n": "06", "file": "06-prompt", "title": "Prompt 定制与多模态",
        "group": "定制篇", "badge": "purple", "time": "8",
        "prev_file": "05-custom-tools.html", "prev_title": "注册自定义工具",
        "next_file": "07-skills.html", "next_title": "使用 Skills",
        "desc": "system_prompt() vs extra_system_prompt()，MultimodalPrompt 图片输入，典型定制场景",
        "goal": "读者能改写 AI 的角色设定、追加行为约束、发送图片给 AI 分析。",
        "content": """
**1. 引言**：默认情况下 Cody 是通用编程助手。本篇讲如何让它成为你想要的专用助手。

**2. system_prompt() —— 替换角色**：
```python
client = (
    Cody()
    .workdir(".")
    .system_prompt(
        "You are a security-focused code review agent. "
        "Always check for OWASP Top 10 vulnerabilities. "
        "Report findings with severity: Critical/High/Medium/Low."
    )
    .build()
)
async with client:
    result = await client.run("Review the authentication module")
```
说明：替换默认的"我是 Cody 编程助手"角色，但保留项目指令（CODY.md）、记忆和 Skills 注入。

**3. extra_system_prompt() —— 追加约束**：
```python
client = (
    Cody()
    .workdir(".")
    .extra_system_prompt(
        "所有回复必须用中文。"
        "代码注释也使用中文。"
        "每次修改文件前先说明修改理由。"
    )
    .build()
)
```
说明：不替换默认角色，只在所有内置 prompt 之后追加。

**4. 两者的区别对比表**：
| | system_prompt() | extra_system_prompt() |
|---|---|---|
| 作用 | 替换默认 persona | 追加额外指令 |
| 保留 CODY.md | ✅ | ✅ |
| 保留记忆/Skills | ✅ | ✅ |
| 适用场景 | 改变 AI 身份 | 添加约束/风格要求 |

**5. 组合使用**：
```python
client = (
    Cody()
    .workdir(".")
    .system_prompt("You are a DevOps assistant specializing in Kubernetes.")
    .extra_system_prompt("Always explain your reasoning before taking action.")
    .tool(my_k8s_tool)
    .build()
)
```

**6. 多模态 Prompt —— 发送图片**：
callout-info：需要模型支持视觉（Claude claude-sonnet-4-0, GPT-4V 等）。
```python
import base64
from cody.core.prompt import MultimodalPrompt, ImageData

with open("screenshot.png", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

prompt = MultimodalPrompt(
    text="根据这个 UI 截图，用 HTML + CSS 实现相同的页面布局",
    images=[ImageData(data=image_b64, media_type="image/png", filename="screenshot.png")]
)

async with client:
    result = await client.run(prompt)
    print(result.output)
```

**7. 多张图片对比**：
```python
prompt = MultimodalPrompt(
    text="对比这两个截图，指出 UI 上的差异",
    images=[
        ImageData(data=before_b64, media_type="image/png", filename="before.png"),
        ImageData(data=after_b64, media_type="image/png", filename="after.png"),
    ]
)
```

**8. 支持的图片格式**：`image/png`, `image/jpeg`, `image/webp`, `image/gif`。

**9. 小结 + 引向第 07 篇**（Skills）。
""",
        "sdk_ref": """
```python
# system_prompt() —— 替换默认 persona（保留 CODY.md/记忆/Skills）
client = Cody().workdir(".").system_prompt("You are a security reviewer.").build()

# extra_system_prompt() —— 在所有内置 prompt 后追加
client = Cody().workdir(".").extra_system_prompt("Always reply in Chinese.").build()

# 组合
client = (
    Cody()
    .workdir(".")
    .system_prompt("You are a DevOps assistant.")
    .extra_system_prompt("Explain your reasoning before acting.")
    .build()
)

# 多模态 Prompt
from cody.core.prompt import MultimodalPrompt, ImageData
import base64

with open("screenshot.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

prompt = MultimodalPrompt(
    text="实现这个页面",
    images=[
        ImageData(
            data=b64,
            media_type="image/png",   # image/png | image/jpeg | image/webp | image/gif
            filename="screenshot.png"
        )
    ]
)

result = await client.run(prompt)
# stream() 同样支持
async for chunk in client.stream(prompt):
    if chunk.type == "text_delta":
        print(chunk.content, end="")
```"""
    },
    {
        "n": "07", "file": "07-skills", "title": "使用 Skills",
        "group": "定制篇", "badge": "purple", "time": "8",
        "prev_file": "06-prompt.html", "prev_title": "Prompt 定制与多模态",
        "next_file": "08-mcp.html", "next_title": "集成 MCP",
        "desc": "Agent Skills 开放标准、四层优先级、list_skills/get_skill、自定义 Skill 目录、编写 SKILL.md",
        "goal": "读者能查询/管理内置 Skills、创建自己的 Skill、配置自定义 Skill 目录。",
        "content": """
**1. 引言**：Skills 是让 AI 懂你的项目的方式——Git 规范、测试框架、部署流程，写成 SKILL.md，AI 自动加载。

**2. Skills 的加载机制**：
四层优先级（从高到低）：
1. 代码中配置的 `skill_dir()`（自定义目录）
2. 项目级：`.cody/skills/`
3. 全局：`~/.cody/skills/`
4. 内置（11 个：git, github, docker, npm, python, rust, go, java, web, cicd, testing）

用图示或列表展示，配 callout-info。

**3. 查询可用 Skills**：
```python
async with AsyncCodyClient(workdir="/my/project") as client:
    skills = await client.list_skills()
    for skill in skills:
        status = "✅ 已启用" if skill["enabled"] else "⬜ 已禁用"
        print(f"  {status} {skill['name']}: {skill['description']} ({skill['source']})")

    # 查看某个 Skill 的完整文档
    git_skill = await client.get_skill("git")
    print(git_skill["documentation"])
```

**4. 创建自定义 Skill**：
```markdown
# .cody/skills/my-team-workflow/SKILL.md
---
name: my-team-workflow
description: 团队代码规范和工作流。处理代码提交、PR 审查和部署时使用。
metadata:
  author: your-team
  version: "1.0"
---
# 团队工作流规范

## 代码提交
- 提交信息格式：`<类型>(<范围>): <描述>`，例：`feat(auth): add JWT refresh token`
- 必须通过 CI 才能合并
- PR 需要至少 1 个 reviewer 批准

## 测试要求
- 新功能必须附带单元测试
- 覆盖率不低于 80%
```
说明 YAML frontmatter 的字段：name（必须）、description（必须，AI 用它决定何时加载）、metadata。

**5. 配置自定义 Skill 目录**（Builder 方式）：
```python
client = (
    Cody()
    .workdir("/my/project")
    .skill_dir("/shared/team-skills")    # 团队共享
    .skill_dir("/home/user/my-skills")   # 个人
    .build()
)
```
环境变量方式：`export CODY_SKILL_DIRS=/shared/team-skills:/home/user/my-skills`

**6. Skills 如何工作**：callout-tip 说明——Skills 自动注入 system prompt，AI 在任务匹配时自动参考，无需手动启用。

**7. 小结 + 引向第 08 篇**（MCP）。
""",
        "sdk_ref": """
```python
# 查询 Skills
skills = await client.list_skills()
# skill: {"name": str, "description": str, "enabled": bool, "source": str}

skill = await client.get_skill("git")
# skill: {"name": str, "description": str, "enabled": bool, "source": str, "documentation": str}

# 自定义 Skill 目录
client = (
    Cody()
    .workdir(".")
    .skill_dir("/shared/team-skills")   # 逐个添加
    .skill_dirs(["/dir1", "/dir2"])      # 批量
    .build()
)

# config() 方式
cfg = config(
    workdir=".",
    skill_dirs=["/shared/team-skills"],
)

# 环境变量
# export CODY_SKILL_DIRS=/shared/team-skills:/home/user/my-skills

# 加载优先级: custom > project(.cody/skills/) > global(~/.cody/skills/) > builtin

# SKILL.md 格式
# ---
# name: skill-name          （必须，小写字母+连字符）
# description: 一句话描述    （必须，AI 用它决定何时加载）
# metadata:
#   author: xxx
#   version: "1.0"
# ---
# # 正文（Markdown）
```"""
    },
    {
        "n": "08", "file": "08-mcp", "title": "集成 MCP",
        "group": "定制篇", "badge": "purple", "time": "10",
        "prev_file": "07-skills.html", "prev_title": "使用 Skills",
        "next_file": "09-security.html", "next_title": "安全与控制",
        "desc": "stdio/HTTP 两种传输、auto_start_mcp、动态添加、mcp_call() 直接调用",
        "goal": "读者能连接 GitHub、飞书、数据库等 MCP 服务器，让 AI 使用这些外部工具。",
        "content": """
**1. 引言**：MCP（Model Context Protocol）是让 AI 访问外部系统的标准协议。一行配置，AI 就能操作 GitHub、飞书文档、数据库等。

**2. 两种传输方式**：
- **stdio**：启动本地子进程（如 npx 运行的 MCP 服务器）
- **HTTP**：连接远程 MCP 端点（如飞书 MCP、Notion MCP）

**3. stdio 示例（连接 GitHub MCP）**：
```python
client = (
    Cody()
    .workdir(".")
    .mcp_stdio_server(
        "github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": "ghp_xxx"}
    )
    .auto_start_mcp(True)  # 首次 run() 自动启动
    .build()
)

async with client:
    result = await client.run("列出我的仓库中最近 5 个未关闭的 Issue")
    print(result.output)
```

**4. HTTP 示例（连接飞书 MCP）**：
```python
client = (
    Cody()
    .workdir(".")
    .mcp_http_server(
        "feishu",
        url="https://mcp.feishu.cn/mcp",
        headers={"X-Lark-MCP-UAT": "your-token"}
    )
    .auto_start_mcp(True)
    .build()
)

async with client:
    result = await client.run("总结这个飞书文档的要点：https://xxx.feishu.cn/docx/xxx")
```

**5. 多个 MCP 服务器**：
```python
client = (
    Cody()
    .mcp_stdio_server("github", command="npx", args=["-y", "@modelcontextprotocol/server-github"], env={"GITHUB_TOKEN": "..."})
    .mcp_http_server("feishu", url="https://mcp.feishu.cn/mcp", headers={...})
    .auto_start_mcp(True)
    .build()
)
```

**6. auto_start_mcp vs 手动启动**：
```python
# 手动启动（控制启动时机）
client = Cody().mcp_http_server("feishu", url="...").build()
async with client:
    await client.start_mcp()  # 明确控制
    result = await client.run("任务")
```

**7. 动态添加 MCP 服务器**（运行时，无需重建 client）：
```python
async with client:
    await client.add_mcp_server(
        name="notion",
        transport="http",
        url="https://mcp.notion.so",
        headers={"Authorization": "Bearer xxx"}
    )
    result = await client.run("整理 Notion 中的待办事项")
```

**8. 直接调用 MCP 工具**：
```python
# 列出所有 MCP 工具
tools = await client.mcp_list_tools()

# 直接调用（格式："服务器名/工具名"）
result = await client.mcp_call("github/list-issues", {"owner": "CodyCodeAgent", "repo": "cody"})
```

**9. 小结 + 引向第 09 篇**（安全与控制）。
""",
        "sdk_ref": """
```python
from cody.sdk import Cody

# stdio 传输（本地子进程）
client = (
    Cody()
    .mcp_stdio_server(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": "ghp_xxx"},
    )
    .auto_start_mcp(True)   # 首次 run() 自动启动，默认 False
    .build()
)

# HTTP 传输（远程端点）
client = (
    Cody()
    .mcp_http_server(
        name="feishu",
        url="https://mcp.feishu.cn/mcp",
        headers={"X-Lark-MCP-UAT": "token"},
    )
    .build()
)

# 手动启动
async with client:
    await client.start_mcp()

# 动态添加（运行时）
async with client:
    await client.add_mcp_server(name="notion", transport="http", url="...", headers={...})
    await client.add_mcp_server(name="gh", command="npx", args=[...], env={...})

# 直接调用 MCP 工具
tools = await client.mcp_list_tools()
result = await client.mcp_call("server-name/tool-name", {"param": "value"})

# SDKConfig 方式
from cody.sdk import SDKConfig, MCPConfig, MCPServerConfig, AsyncCodyClient
cfg = SDKConfig(
    mcp=MCPConfig(servers=[
        MCPServerConfig(name="feishu", transport="http", url="..."),
        MCPServerConfig(name="github", transport="stdio", command="npx", args=[...]),
    ])
)
async with AsyncCodyClient(config=cfg, auto_start_mcp=True) as client:
    ...
```"""
    },
    {
        "n": "09", "file": "09-security", "title": "安全与控制",
        "group": "进阶篇", "badge": "yellow", "time": "10",
        "prev_file": "08-mcp.html", "prev_title": "集成 MCP",
        "next_file": "10-events.html", "next_title": "事件与可观测性",
        "desc": "allowed_roots 多目录访问控制、strict_read_boundary、熔断器配置、无状态模式",
        "goal": "读者能设置文件访问边界、配置熔断保护防止失控 Agent、在 CI/无状态环境使用 Cody。",
        "content": """
**1. 引言**：AI Agent 能写文件、执行命令——权力越大，需要的护栏就越多。本篇介绍 Cody 的三层安全机制。

**2. 文件访问边界：allowed_roots**

默认情况下，写操作仅限于 `workdir`。通过 `allowed_roots` 扩展允许范围：

```python
# 场景：Monorepo，主项目需要访问共享库
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
```

展示前后端联调场景的示例。

**3. strict_read_boundary**：

```python
# 默认：读操作不受边界限制，写操作受限
# 开启后：读和写都限制在边界内
client = (
    Cody()
    .workdir("/workspace/project")
    .allowed_root("/workspace/shared")
    .strict_read_boundary()   # 开启严格读边界
    .build()
)
```
callout-info：开启后 AI 尝试读取边界外文件时会收到明确拒绝信息，自动调整路径重试。

**4. 熔断器（Circuit Breaker）**

说明熔断器的作用：防止失控 Agent 消耗过多资源（token/费用/死循环）。

触发条件表：
| 条件 | 默认值 | 配置项 |
|------|--------|--------|
| Token 超限 | 1,000,000 | max_tokens |
| 成本超限 | $10.00 | max_cost_usd |
| 步数超限 | 0（无限制） | max_steps |
| 死循环 | 连续 6 次相似结果 | loop_detect_turns |

```python
from cody.sdk import CircuitBreakerConfig
from cody.core.errors import CircuitBreakerError

client = (
    Cody()
    .workdir(".")
    .circuit_breaker(
        max_tokens=200_000,
        max_cost_usd=2.0,
        max_steps=30,
        loop_detect_turns=5,
    )
    .build()
)

# run() 场景：抛出异常
try:
    result = await client.run("复杂的大规模重构任务")
except CircuitBreakerError as e:
    print(f"熔断: {e.reason}")  # token_limit / cost_limit / loop / step_limit
    print(f"已用: {e.tokens_used} tokens, ${e.cost_usd:.4f}")

# stream() 场景：yield circuit_breaker 事件
async for chunk in client.stream("任务"):
    if chunk.type == "circuit_breaker":
        print(f"熔断: {chunk.content}")
        break
```

**5. 无状态模式**

适用场景：CI/CD 脚本、Serverless、测试（不想留下任何文件）。

```python
client = Cody().workdir(".").stateless().build()

async with client:
    result = await client.run("分析代码质量")
    # 不会创建 sessions.db / audit.db 等文件
```

callout-tip：`.stateless()` 之后可以覆盖个别存储组件（如仍保留审计日志）。

**6. 小结 + 引向第 10 篇**。
""",
        "sdk_ref": """
```python
# allowed_roots
client = (
    Cody()
    .workdir("/workspace/app")
    .allowed_root("/workspace/shared")        # 逐个添加
    .allowed_roots(["/workspace/shared", "/workspace/proto"])  # 批量
    .build()
)

# strict_read_boundary（v1.9.2+）
client = Cody().workdir(".").strict_read_boundary().build()

# SecurityConfig 方式
from cody.sdk import SDKConfig, SecurityConfig
cfg = SDKConfig(
    workdir="/workspace/project",
    security=SecurityConfig(
        allowed_roots=["/workspace/shared"],
        strict_read_boundary=True,
        blocked_commands=["rm -rf", "git push --force"],
    ),
)

# 熔断器
from cody.sdk import CircuitBreakerConfig
from cody.core.errors import CircuitBreakerError

client = Cody().circuit_breaker(
    max_tokens=500_000,
    max_cost_usd=5.0,
    max_steps=50,
    loop_detect_turns=5,
    loop_similarity_threshold=0.9,
).build()

# 捕获熔断（run）
try:
    result = await client.run("任务")
except CircuitBreakerError as e:
    e.reason        # "token_limit" / "cost_limit" / "loop" / "step_limit"
    e.tokens_used   # int
    e.cost_usd      # float

# 处理熔断（stream）
async for chunk in client.stream("任务"):
    if chunk.type == "circuit_breaker":
        print(chunk.content)  # 原因描述
        break

# 无状态模式（v1.11.0+）
client = Cody().workdir(".").stateless().build()
# 不写入任何磁盘文件（sessions.db / audit.db / file_history.db）
```"""
    },
    {
        "n": "10", "file": "10-events", "title": "事件与可观测性",
        "group": "进阶篇", "badge": "yellow", "time": "8",
        "prev_file": "09-security.html", "prev_title": "安全与控制",
        "next_file": "11-memory.html", "next_title": "项目记忆",
        "desc": "EventType 全量枚举、.on()/.on_async() 注册、指标收集 get_metrics()、监控工具调用",
        "goal": "读者能监听 AI 运行过程中的所有事件，采集 token/cost/工具调用等指标。",
        "content": """
**1. 引言**：在生产环境中，你需要知道 AI 在做什么、花了多少、有没有出错。事件系统和指标收集解决这个问题。

**2. 事件系统基础**：

```python
from cody.sdk import Cody, EventType

client = (
    Cody()
    .workdir(".")
    .on(EventType.TOOL_CALL, lambda e: print(f"→ 调用工具: {e.tool_name}({list(e.args.keys())})"))
    .on(EventType.TOOL_RESULT, lambda e: print(f"← {e.tool_name}: {e.result[:80]}"))
    .on(EventType.RUN_END, lambda e: print(f"✓ 完成: {e.result[:100]}"))
    .build()
)

async with client:
    await client.run("分析项目结构")
```
说明：Builder 上链式调用 `.on()` 会自动启用事件系统。

**3. 所有 EventType**（表格）：
| 事件 | 触发时机 |
|------|---------|
| RUN_START / RUN_END / RUN_ERROR | 任务生命周期 |
| TOOL_CALL / TOOL_RESULT / TOOL_ERROR | 工具调用 |
| THINKING_START / THINKING_CHUNK / THINKING_END | 思考过程 |
| STREAM_START / STREAM_CHUNK / STREAM_END | 流式输出 |
| SESSION_CREATE / SESSION_CLOSE | 会话管理 |
| CONTEXT_COMPACT | 上下文压缩 |

**4. 字符串形式注册**（也可以用字符串代替枚举）：
```python
client.on("tool_call", lambda e: ...)
client.on("run_end", lambda e: ...)
```

**5. 异步事件处理器**：
```python
async def async_handler(event):
    await db.insert_event(event.tool_name, event.args)

client = Cody().workdir(".").enable_events().build()
client.on_async(EventType.TOOL_CALL, async_handler)
```

**6. 指标收集**：
```python
client = Cody().workdir(".").enable_metrics().build()

async with client:
    await client.run("分析项目")
    await client.run("生成报告")

    metrics = client.get_metrics()
    print(f"总 Token: {metrics['total_tokens']}")
    print(f"工具调用次数: {metrics['total_tool_calls']}")
    print(f"总耗时: {metrics['total_duration']:.2f}s")
    print(f"估计成本: ${metrics.get('estimated_cost_usd', 0):.4f}")
```

**7. 实用示例：记录所有工具调用到日志**：
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cody.tools")

client = (
    Cody()
    .workdir(".")
    .on(EventType.TOOL_CALL, lambda e: logger.info(f"TOOL_CALL {e.tool_name} {e.args}"))
    .on(EventType.TOOL_ERROR, lambda e: logger.error(f"TOOL_ERROR {e.tool_name}: {e.error}"))
    .on(EventType.RUN_ERROR, lambda e: logger.error(f"RUN_ERROR: {e.error}"))
    .build()
)
```

**8. 小结 + 引向第 11 篇**（项目记忆）。
""",
        "sdk_ref": """
```python
from cody.sdk import Cody, EventType

# Builder 链式注册（自动启用 events）
client = (
    Cody()
    .workdir(".")
    .on("tool_call", lambda e: print(e.tool_name))        # 字符串形式
    .on(EventType.TOOL_RESULT, lambda e: print(e.result)) # 枚举形式
    .build()
)

# 构造后注册
client = Cody().workdir(".").enable_events().build()
client.on(EventType.RUN_END, lambda e: print(e.result))
client.on_async(EventType.TOOL_CALL, async_handler)  # 异步处理器

# 所有 EventType
EventType.RUN_START    # e.prompt
EventType.RUN_END      # e.result
EventType.RUN_ERROR    # e.error
EventType.TOOL_CALL    # e.tool_name, e.args
EventType.TOOL_RESULT  # e.tool_name, e.result
EventType.TOOL_ERROR   # e.tool_name, e.error
EventType.THINKING_START
EventType.THINKING_CHUNK  # e.content
EventType.THINKING_END
EventType.STREAM_START
EventType.STREAM_CHUNK    # e.content
EventType.STREAM_END
EventType.SESSION_CREATE  # e.session_id
EventType.SESSION_CLOSE
EventType.CONTEXT_COMPACT

# 指标收集
client = Cody().workdir(".").enable_metrics().build()
metrics = client.get_metrics()
# metrics: {"total_tokens": int, "total_tool_calls": int, "total_duration": float, ...}
```"""
    },
    {
        "n": "11", "file": "11-memory", "title": "项目记忆",
        "group": "进阶篇", "badge": "yellow", "time": "7",
        "prev_file": "10-events.html", "prev_title": "事件与可观测性",
        "next_file": "12-human-in-loop.html", "next_title": "人机协同",
        "desc": "四类记忆分类、add_memory/get_memory/clear_memory、跨会话自动注入机制",
        "goal": "读者能让 AI 在不同任务间积累和复用项目经验，减少重复解释。",
        "content": """
**1. 引言**：每次对话 AI 都忘掉上次的决策？项目记忆让 AI 在不同会话间保留项目知识。

**2. 四类记忆分类**：
| 类别 | 说明 | 示例 |
|------|------|------|
| conventions | 代码风格、命名规范 | "使用 ruff 格式化，行宽 100" |
| patterns | 设计模式、常用工具 | "用 Factory 模式创建 handler" |
| issues | 已知 bug、注意事项 | "SQLite 并发写入需 WAL 模式" |
| decisions | 架构选择、技术决策 | "选择 FastAPI 而非 Flask" |

**3. 写入记忆**：
```python
async with AsyncCodyClient(workdir="/my/project") as client:
    # 记录项目约定
    await client.add_memory(
        category="conventions",
        content="代码必须通过 ruff check，行宽 100，使用 pydantic v2 模型",
        confidence=0.95,
        tags=["lint", "code-style"],
    )

    # 记录重要决策
    await client.add_memory(
        category="decisions",
        content="选择 pydantic-ai 作为 Agent 框架，原因：类型安全、工具注册简单",
        confidence=0.9,
    )

    # 记录已知问题
    await client.add_memory(
        category="issues",
        content="sub_agent.py 使用延迟导入避免循环依赖，不要改成顶层导入",
        confidence=0.99,
    )
```

**4. 读取记忆**：
```python
    memory = await client.get_memory()
    for category, entries in memory.items():
        print(f"\\n=== {category} ===")
        for entry in entries:
            tags = ", ".join(entry.get("tags", []))
            print(f"  [{entry['confidence']:.0%}] {entry['content']}")
            if tags:
                print(f"       标签: {tags}")
```

**5. 工作原理说明**：callout-info 框——
- 存储位置：`~/.cody/memory/<project_hash>/`（按 workdir 隔离）
- 每次 `run()` 时自动加载，注入到 system prompt 的 "Project Memory" 段
- 每类最多 50 条，超出自动淘汰最旧的
- 置信度 < 0.3 的条目不会注入 prompt

**6. 清除记忆**：
```python
    await client.clear_memory()
    print("项目记忆已清除")
```

**7. 实用场景**：在文章末尾给出一个实际场景——新人加入项目，用 AI 自动学习项目规范并存储为记忆，后续任务自动遵循。

**8. 小结 + 引向第 12 篇**。
""",
        "sdk_ref": """
```python
# 写入记忆
await client.add_memory(
    category="conventions",   # "conventions" | "patterns" | "issues" | "decisions"
    content="规范内容描述",
    confidence=0.9,           # 0.0-1.0，< 0.3 不会注入 prompt
    tags=["lint", "style"],   # 可选
    source_task_id=None,      # 可选，关联任务 ID
    source_task_title=None,   # 可选
)

# 读取所有记忆
memory = await client.get_memory()
# memory: {"conventions": [...], "patterns": [...], "issues": [...], "decisions": [...]}
# 每条: {"content": str, "confidence": float, "tags": list, "created_at": str, ...}

# 清除记忆
await client.clear_memory()

# 存储位置：~/.cody/memory/<md5(workdir)>/
# 文件：conventions.json / patterns.json / issues.json / decisions.json
# 每类最多 50 条，超出自动淘汰最旧的
# confidence < 0.3 的条目不注入 system prompt
```"""
    },
    {
        "n": "12", "file": "12-human-in-loop", "title": "人机协同",
        "group": "进阶篇", "badge": "yellow", "time": "8",
        "prev_file": "11-memory.html", "prev_title": "项目记忆",
        "next_file": "13-storage.html", "next_title": "存储抽象",
        "desc": "interaction_request 事件监听、submit_interaction() 响应、三种场景、超时处理",
        "goal": "读者能实现需要人工确认的 AI 工作流：AI 提问、人类回答，或 AI 修改文件前等待确认。",
        "content": """
**1. 引言**：有些任务不能让 AI 全自主——删除文件前需要确认，需要人提供上下文信息。人机协同让 AI 在关键节点暂停等待。

**2. 两种触发场景**：
- **question 工具**：AI 主动提问（"这个函数应该抛出异常还是返回 None？"）
- **CONFIRM 级工具**：`exec_command`、`write_file`、`edit_file` 在执行前等待批准

**3. 开启配置**：
```python
client = Cody().workdir(".").interaction(enabled=True, timeout=30).build()
```
callout-warn：默认 `interaction.enabled=False`，所有操作自动批准。开启后才会暂停等待。

**4. 完整流式处理示例**：
```python
import asyncio
from cody.sdk import Cody
from cody.core.errors import InteractionTimeoutError

client = Cody().workdir(".").interaction(enabled=True, timeout=60).build()

async with client:
    try:
        async for chunk in client.stream("帮我重构 auth.py，删除旧的 MD5 密码哈希"):
            if chunk.type == "interaction_request":
                # AI 在等你
                print(f"\\n[{chunk.interaction_kind}] {chunk.content}")
                if chunk.options:
                    for i, opt in enumerate(chunk.options, 1):
                        print(f"  {i}. {opt}")

                # 读取用户输入
                user_input = input("\\n你的回应: ").strip()

                # 提交响应
                await client.submit_interaction(
                    request_id=chunk.request_id,
                    action="answer",   # "answer" / "approve" / "reject" / "revise"
                    content=user_input,
                )
            elif chunk.type == "text_delta":
                print(chunk.content, end="", flush=True)
    except InteractionTimeoutError:
        print("\\n[超时] AI 等待响应超过了设定时间，任务已终止")
```

**5. 三种 interaction_kind**：
| kind | 场景 | 常用 action |
|------|------|------------|
| question | AI 提问，需要回答 | answer |
| confirm | 工具执行前确认 | approve / reject |
| feedback | 请求结构化反馈 | approve / reject / revise |

**6. submit_interaction 参数说明**：
- `request_id`：来自 chunk.request_id，必须匹配
- `action`：`"answer"` / `"approve"` / `"reject"` / `"revise"`
- `content`：回答内容或修订说明

**7. 超时行为**：callout-info——超过 timeout 秒未响应，抛出 `InteractionTimeoutError`，任务终止。默认 30 秒。

**8. 同步版注意事项**：callout-warn——`CodyClient`（同步版）不支持人机协同，始终自动批准。

**9. 小结 + 引向第 13 篇**（存储抽象）。
""",
        "sdk_ref": """
```python
# 开启人机协同
client = Cody().workdir(".").interaction(enabled=True, timeout=30).build()

# 流式处理 interaction_request
async for chunk in client.stream("任务"):
    if chunk.type == "interaction_request":
        chunk.request_id        # str，必须用于 submit_interaction
        chunk.interaction_kind  # "question" | "confirm" | "feedback"
        chunk.content           # str，提示文字
        chunk.options           # list[str] | None，可选项

        await client.submit_interaction(
            request_id=chunk.request_id,
            action="answer",    # "answer" | "approve" | "reject" | "revise"
            content="用户的回答",
        )

# 捕获超时
from cody.core.errors import InteractionTimeoutError
try:
    async for chunk in client.stream("任务"): ...
except InteractionTimeoutError as e:
    print(f"超时: {e}")

# 行为对比
# interaction.enabled=False（默认）: CONFIRM 级工具自动批准，不暂停
# interaction.enabled=True:          CONFIRM 级工具暂停，等待人类 approve/reject
# CodyClient（同步版）:              始终自动批准，不支持人机协同

# 三种场景
# question: AI 提问，action="answer", content="你的回答"
# confirm:  执行前确认，action="approve"（继续）或 "reject"（取消）
# feedback: 结构化反馈，action="approve"/"reject"/"revise", content="修订说明"
```"""
    },
    {
        "n": "13", "file": "13-storage", "title": "存储抽象",
        "group": "进阶篇", "badge": "yellow", "time": "8",
        "prev_file": "12-human-in-loop.html", "prev_title": "人机协同",
        "next_file": "",  "next_title": "",
        "desc": "三个 Protocol 接口、自定义 SessionStore/AuditLogger/FileHistory、错误处理体系",
        "goal": "读者能将默认 SQLite 存储替换为自己的实现（PostgreSQL、Redis 等），并正确处理 SDK 错误。",
        "content": """
**1. 引言**：默认 Cody 用 SQLite 存储会话、审计日志和文件历史。生产环境可能需要 PostgreSQL、DynamoDB 或自定义实现——本篇讲如何替换。

**2. 三个存储组件**（表格）：
| Protocol | 默认实现 | 默认存储位置 | 职责 |
|----------|---------|------------|------|
| SessionStoreProtocol | SessionStore (SQLite) | ~/.cody/sessions.db | 会话和消息历史 |
| AuditLoggerProtocol | AuditLogger (SQLite) | ~/.cody/audit.db | 工具调用审计记录 |
| FileHistoryProtocol | FileHistory (SQLite) | .cody/file_history.db | 文件修改 undo/redo |

**3. 自定义 SessionStore**（完整示例，模拟 PostgreSQL 实现）：
```python
from cody.core.storage import SessionStoreProtocol

class PostgresSessionStore:
    """满足 SessionStoreProtocol 的 PostgreSQL 实现。"""
    def __init__(self, conn_string: str):
        self.conn_string = conn_string

    def close(self):
        # 关闭连接池
        pass

    def create_session(self, title="", model="", workdir=""):
        # INSERT INTO sessions ... RETURNING id, title, created_at
        # 返回 SessionInfo 对象（有 .id 属性）
        return SimpleNamespace(id="ses_" + generate_id(), title=title)

    def add_message(self, session_id, role, content, images=None):
        # INSERT INTO messages ...
        pass

    def get_session(self, session_id):
        # SELECT * FROM sessions WHERE id = session_id
        # 返回 SessionDetail 对象（有 .messages 属性）
        pass

    def list_sessions(self, limit=20):
        # SELECT * FROM sessions ORDER BY created_at DESC LIMIT limit
        # 返回 list[SessionInfo]
        pass

    def delete_session(self, session_id):
        pass

    # ... 其余方法见 SessionStoreProtocol 接口

# 注入自定义实现
client = (
    Cody()
    .workdir(".")
    .session_store(PostgresSessionStore("postgresql://..."))
    .build()
)
```

**4. 注入方式**：
```python
client = (
    Cody()
    .session_store(my_session_store)
    .audit_logger(my_audit_logger)
    .file_history(my_file_history)
    .build()
)
```
callout-tip：三者独立，可以只替换其中一个，其余保持 SQLite 默认实现。

**5. 与无状态模式的关系**：
callout-info：`.stateless()` 是快捷方式，等同于注入三个 Null 实现。`.stateless()` 之后仍可覆盖个别组件。

**6. 完整错误处理体系**（错误类型表）：
| 异常 | 说明 |
|------|------|
| CodyError | 基础异常，所有 Cody 错误的父类 |
| CodyModelError | 模型 API 调用失败 |
| CodyToolError | 工具执行失败，e.details['tool_name'] |
| CodyPermissionError | 文件路径越界等权限问题 |
| CodyRateLimitError | API 速率限制，e.retry_after 秒后重试 |
| CodyConfigError | 配置错误（缺少 API Key 等） |
| CodyTimeoutError | 请求超时 |
| CodyConnectionError | 网络连接失败 |
| CodySessionError | 会话不存在或格式错误 |

```python
from cody.sdk import (
    CodyError, CodyModelError, CodyToolError,
    CodyPermissionError, CodyRateLimitError,
    CodyConfigError, CodyTimeoutError, CodyConnectionError,
)

try:
    result = await client.run("任务")
except CodyRateLimitError as e:
    await asyncio.sleep(e.retry_after)
    result = await client.run("任务")  # 重试
except CodyToolError as e:
    print(f"工具 {e.details['tool_name']} 执行失败: {e.message}")
except CodyPermissionError as e:
    print(f"权限拒绝: {e.message}")
except CodyError as e:
    print(f"[{e.code}] {e.message}")  # 兜底
```

**7. 系列总结**：congratulations，本篇是 SDK 教程系列的最后一篇。给出学习路线回顾和指向 GitHub 深入阅读的建议。
""",
        "sdk_ref": """
```python
# 三个 Protocol 接口（runtime_checkable，支持 isinstance 检查）
from cody.core.storage import (
    SessionStoreProtocol,   # 会话存储
    AuditLoggerProtocol,    # 审计日志
    FileHistoryProtocol,    # 文件历史
)

# 注入自定义实现（满足对应 Protocol 接口即可）
client = (
    Cody()
    .session_store(my_session_store)
    .audit_logger(my_audit_logger)
    .file_history(my_file_history)
    .build()
)

# SessionStoreProtocol 需要实现的方法：
# close() / create_session(title, model, workdir) / add_message(session_id, role, content, images)
# get_session(session_id) / list_sessions(limit) / delete_session(session_id)
# get_latest_session(workdir) / get_message_count(session_id) / update_title(session_id, title)

# 与无状态模式的关系
client = Cody().stateless().build()                          # 全部 Null
client = Cody().stateless().audit_logger(real_logger).build() # 覆盖个别

# 完整错误体系
from cody.sdk import (
    CodyError,           # 基础异常
    CodyModelError,      # 模型 API 失败
    CodyToolError,       # 工具执行失败（e.details['tool_name']）
    CodyPermissionError, # 权限拒绝（路径越界等）
    CodyNotFoundError,   # 资源不存在
    CodyRateLimitError,  # 速率限制（e.retry_after: int 秒）
    CodyConfigError,     # 配置错误
    CodyTimeoutError,    # 超时
    CodyConnectionError, # 连接失败
    CodySessionError,    # 会话错误
)

# e.code    → str，错误码
# e.message → str，错误描述
```"""
    },
]

# ── HTML 模板生成器 ────────────────────────────────────────────────────────────

SIDEBAR = """    <div class="tutorial-back-link"><a href="../sdk.html">← 返回 SDK 教程</a></div>
    <div class="sidebar-section">
      <div class="sidebar-section-title">基础篇</div>
      <ul class="sidebar-nav">
        <li><a href="01-single-run.html"{a01}>01. 一次性对话</a></li>
        <li><a href="02-multi-turn.html"{a02}>02. 多轮对话</a></li>
        <li><a href="03-streaming.html"{a03}>03. 流式输出全解</a></li>
      </ul>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-section-title">工具篇</div>
      <ul class="sidebar-nav">
        <li><a href="04-tools.html"{a04}>04. 工具直接调用</a></li>
        <li><a href="05-custom-tools.html"{a05}>05. 注册自定义工具</a></li>
      </ul>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-section-title">定制篇</div>
      <ul class="sidebar-nav">
        <li><a href="06-prompt.html"{a06}>06. Prompt 定制与多模态</a></li>
        <li><a href="07-skills.html"{a07}>07. 使用 Skills</a></li>
        <li><a href="08-mcp.html"{a08}>08. 集成 MCP</a></li>
      </ul>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-section-title">进阶篇</div>
      <ul class="sidebar-nav">
        <li><a href="09-security.html"{a09}>09. 安全与控制</a></li>
        <li><a href="10-events.html"{a10}>10. 事件与可观测性</a></li>
        <li><a href="11-memory.html"{a11}>11. 项目记忆</a></li>
        <li><a href="12-human-in-loop.html"{a12}>12. 人机协同</a></li>
        <li><a href="13-storage.html"{a13}>13. 存储抽象</a></li>
      </ul>
    </div>"""


def build_sidebar(active_n):
    s = SIDEBAR
    for n in ["01","02","03","04","05","06","07","08","09","10","11","12","13"]:
        placeholder = f"{{a{n}}}"
        replacement = ' class="active"' if n == active_n else ""
        s = s.replace(placeholder, replacement)
    return s


def build_prevnext(article):
    prev_file = article.get("prev_file", "")
    prev_title = article.get("prev_title", "")
    next_file = article.get("next_file", "")
    next_title = article.get("next_title", "")

    prev_btn = ""
    if prev_file:
        prev_btn = f'''      <a href="{prev_file}" class="prev-next-btn">
        <span class="direction">← 上一篇</span>
        <span class="pn-title">{prev_title}</span>
      </a>'''
    else:
        prev_btn = "      <div></div>"

    next_btn = ""
    if next_file:
        next_btn = f'''      <a href="{next_file}" class="prev-next-btn next">
        <span class="direction">下一篇 →</span>
        <span class="pn-title">{next_title}</span>
      </a>'''
    else:
        next_btn = "      <div></div>"

    return f'''    <div class="article-prev-next">
{prev_btn}
{next_btn}
    </div>'''


def build_html_template(article):
    n = article["n"]
    title = article["title"]
    group = article["group"]
    badge = article["badge"]
    time_ = article["time"]
    filename = article["file"] + ".html"

    sidebar_html = build_sidebar(n)
    prevnext_html = build_prevnext(article)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{n}. {title} – Cody SDK 教程</title>
  <meta name="description" content="{article['desc']}">
  <meta name="theme-color" content="#0a0e1a">
  <link rel="icon" type="image/svg+xml" href="../favicon.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../style.css">
  <script>document.documentElement.classList.add('js');</script>
</head>
<body>
<nav class="navbar" role="navigation" aria-label="主导航">
  <div class="nav-inner">
    <a href="../index.html" class="nav-logo" aria-label="Cody 首页">
      <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect width="64" height="64" rx="14" fill="#0a0e1a"/><circle cx="32" cy="32" r="22" stroke="#52c4f7" stroke-width="2" stroke-dasharray="4 2" opacity="0.4"/><path d="M20 25 L13 32 L20 39" stroke="#52c4f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M44 25 L51 32 L44 39" stroke="#52c4f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/><rect x="27" y="27" width="10" height="10" rx="2" fill="#52c4f7" transform="rotate(45 32 32)"/><line x1="21" y1="32" x2="26" y2="32" stroke="#52c4f7" stroke-width="1.5" opacity="0.6"/><line x1="38" y1="32" x2="43" y2="32" stroke="#52c4f7" stroke-width="1.5" opacity="0.6"/></svg>
      Cody
    </a>
    <ul class="nav-links" role="list">
      <li><a href="../index.html">首页</a></li>
      <li><a href="../docs.html" class="active">文档</a></li>
      <li><a href="../sdk.html">SDK 教程</a></li>
      <li><a href="https://github.com/CodyCodeAgent/cody/blob/main/CHANGELOG.md" target="_blank" rel="noopener">更新日志</a></li>
      <li><a href="https://github.com/CodyCodeAgent/cody" target="_blank" rel="noopener">GitHub ↗</a></li>
    </ul>
    <div class="nav-actions">
      <a href="../sdk.html" class="btn btn-ghost">← SDK 教程</a>
      <a href="https://github.com/CodyCodeAgent/cody" class="btn btn-primary" target="_blank" rel="noopener">GitHub</a>
    </div>
    <button class="hamburger" aria-label="切换菜单" aria-expanded="false"><span></span><span></span><span></span></button>
  </div>
</nav>
<div class="docs-layout">
  <aside class="docs-sidebar" role="complementary" aria-label="教程导航">
{sidebar_html}
  </aside>
  <main class="docs-content" id="main-content">
    <div class="article-breadcrumb"><a href="../docs.html">文档中心</a> / <a href="../sdk.html">SDK 教程</a> / <span>{group}</span></div>
    <h1>{title}</h1>
    <div class="article-meta">
      <span class="badge badge-{badge}">{group}</span>
      <span class="badge badge-green">第 {n} 篇</span>
      <span class="reading-time">📖 约 {time_} 分钟</span>
    </div>

    <!-- ARTICLE CONTENT START -->
    <!-- ARTICLE CONTENT END -->

{prevnext_html}
  </main>
</div>
<footer>
  <div class="container">
    <div class="footer-inner">
      <div class="footer-brand">
        <a href="../index.html" class="nav-logo" style="font-size:1rem"><svg width="24" height="24" viewBox="0 0 64 64" fill="none" aria-hidden="true"><rect width="64" height="64" rx="14" fill="#0a0e1a"/><circle cx="32" cy="32" r="22" stroke="#52c4f7" stroke-width="2" stroke-dasharray="4 2" opacity="0.4"/><path d="M20 25 L13 32 L20 39" stroke="#52c4f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M44 25 L51 32 L44 39" stroke="#52c4f7" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/><rect x="27" y="27" width="10" height="10" rx="2" fill="#52c4f7" transform="rotate(45 32 32)"/></svg> Cody</a>
        <p>开源 AI Coding Agent 框架。</p>
      </div>
      <div class="footer-group"><h4>SDK 教程</h4><ul><li><a href="../sdk.html">全部 13 篇 →</a></li></ul></div>
      <div class="footer-group"><h4>资源</h4><ul><li><a href="https://github.com/CodyCodeAgent/cody" target="_blank" rel="noopener">GitHub</a></li><li><a href="https://pypi.org/project/cody-ai/" target="_blank" rel="noopener">PyPI</a></li></ul></div>
    </div>
    <div class="footer-bottom"><span>© 2026 Cody Contributors · MIT License</span></div>
  </div>
</footer>
<script src="../script.js"></script>
</body>
</html>"""


# ── 生成 Prompt 文件 ──────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """# Prompt：Cody SDK 教程第 {n} 篇 —— {title}

## 任务说明

你是技术写作专家，为 Cody 开源 AI Coding Agent 框架编写 SDK 实战教程。

产出文件：`pages/sdk/{filename}`

**操作方式**：将下方"HTML 模板"中 `<!-- ARTICLE CONTENT START -->` 到 `<!-- ARTICLE CONTENT END -->` 之间的注释行，替换为本篇教程的完整正文 HTML。不要修改模板的其他任何部分。直接输出完整 HTML，不要任何说明文字。

---

## Cody 项目简介

Cody 是开源 AI Coding Agent 框架（Python），`pip install cody-ai`。`AsyncCodyClient` 是主 SDK 入口，直接包装 core 引擎（in-process）。GitHub: https://github.com/CodyCodeAgent/cody

---

## 设计规范（正文中使用的 HTML 组件）

**代码块**（必须带 Copy 按钮）：
```html
<div class="code-block">
  <button class="copy-btn" aria-label="复制代码">Copy</button>
  <pre>代码，用 span 做语法高亮</pre>
</div>
```

**语法高亮**（用在 pre 内）：
- `.kw` → 红色，关键字：`from import async await def class with try except raise`
- `.fn` → 紫色，函数名
- `.str` → 蓝色，字符串
- `.cm` → 灰斜，注释（`# xxx`）
- `.nb` → 橙色，内置函数/参数名

**提示框**：`<div class="callout callout-tip/info/warn">内容</div>`

**参数/对比表**：
```html
<table class="param-table">
  <thead><tr><th>列1</th><th>列2</th></tr></thead>
  <tbody><tr><td>值1</td><td>值2</td></tr></tbody>
</table>
```

**徽章**：`<span class="badge badge-blue/green/purple/yellow">文字</span>`

**内联代码**：`<code>client.run()</code>`

**小标题**：`<h2 id="anchor">标题</h2>` 和 `<h3>小标题</h3>`

---

## 本篇学习目标

{goal}

---

## 正文内容要求

{content}

---

## SDK 准确参考资料（请严格以此为准，不要编造不存在的 API）

{sdk_ref}

---

## HTML 模板（填写 ARTICLE CONTENT 部分后输出完整文件）

```html
{html_template}
```
"""


for article in ARTICLES:
    html_template = build_html_template(article)
    prompt_content = PROMPT_TEMPLATE.format(
        n=article["n"],
        title=article["title"],
        filename=article["file"] + ".html",
        goal=article["goal"].strip(),
        content=article["content"].strip(),
        sdk_ref=article["sdk_ref"].strip(),
        html_template=html_template,
    )

    outfile = os.path.join(OUTDIR, f"sdk-{article['n']}-{article['file'].split('-', 1)[1]}.md")
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(prompt_content)
    print(f"✓ {outfile}")

print(f"\n共生成 {len(ARTICLES)} 个 prompt 文件")
