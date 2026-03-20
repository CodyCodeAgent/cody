# Cody Agent 内核 & SDK 深度审查

> 审查日期：2026-03-20 | 版本：v1.11.0
> 定位：Cody 是可嵌入的 AI Agent 框架/SDK，Core + SDK 是产品，CLI/TUI/Web 是参考实现。

---

## 一、Agent 内核对比（Cody vs opencode）

### 1. 执行循环

| 维度 | Cody | opencode |
|------|------|----------|
| 模式 | pydantic-ai 内置的 ReAct 循环 | Vercel AI SDK `streamText()` + 外层 session 循环 |
| 控制力 | 循环由 pydantic-ai 内部管理，Cody 无法介入每一步 | 双层循环，外层可介入 compaction/subtask 调度 |
| 流式 | `run_stream()` 逐事件返回 | `streamText()` 逐 token 返回 |

**差距：** Cody 把执行循环完全委托给 pydantic-ai，无法在每个 step 之间插入自定义逻辑（如中间检查、动态调整策略）。opencode 的双层循环让它可以在每步之间做 compaction 检查、subtask 调度、doom loop 检测。

**建议：** 考虑在 `runner.py` 中包装 pydantic-ai 的循环，增加 **step hook**，让 SDK 消费者能在每步之间注入逻辑。

---

### 2. 任务拆分 / 子 Agent

| 维度 | Cody | opencode |
|------|------|----------|
| 子 Agent 类型 | 4 种（code/research/test/generic） | 2 种 subagent（general/explore）+ 2 种 primary（build/plan） |
| 并行执行 | `spawn_agent()` + `SubAgentManager`，最多 5 并发，300s 超时 | `task` 工具创建子 session，AI SDK 原生并行工具调用 |
| 子 Agent 通信 | 返回文本结果给主 Agent | 返回文本结果，支持 `task_id` 恢复已有子 session |
| 子 Agent 隔离 | 独立 runner，共享 config | 独立子 session，有 `parentID` 追踪 |

**Cody 优势：**
- `SubAgentManager` 有明确的并发上限（5）和超时（300s）
- 4 种类型比 opencode 的 2 种 subagent 更细分
- `get_agent_status()` / `kill_agent()` 提供了子 Agent 生命周期控制

**差距：**
- opencode 的子 session 可以**恢复**（通过 `task_id`），Cody 的子 Agent 是一次性的
- opencode 子 Agent 权限可**独立配置**（deny todowrite 避免与父冲突），Cody 的子 Agent 继承父配置

**建议：** 子 Agent 可恢复能力对长任务很有价值，考虑支持。子 Agent 独立权限配置也应增加。

---

### 3. 上下文管理

| 维度 | Cody | opencode |
|------|------|----------|
| Compaction 触发 | 接近 token 限制时自动触发 | 每步后检查：`token >= input_limit - reserved` |
| 策略 | 截断 + LLM 摘要（两种可选） | LLM 摘要（结构化模板：Goal/Instructions/Discoveries/Accomplished/Files） |
| 工具输出裁剪 | 无 | **有**：保护最近 40K tokens 的工具输出，旧的标记为 compacted |
| 工具输出截断 | 无 | **有**：每个工具输出自动截断，超长内容写入临时文件返回路径 |
| Compaction 后恢复 | 替换历史消息 | 注入合成用户消息 "Continue if you have next steps" 自动恢复 |

**关键差距：**

1. **工具输出截断（Tool Output Truncation）**— 这是 opencode 的一个重要设计。每个工具的返回值都经过自动截断处理，超长输出写入临时文件。Cody 没有这个机制，一个 `grep` 返回大量结果时会直接撑爆上下文。

2. **结构化 Compaction 模板** — opencode 的 compaction prompt 要求按固定结构输出（Goal/Instructions/Discoveries/Accomplished/Relevant Files），这比 Cody 的 "300 words or fewer" 泛化摘要能保留更多关键信息。

3. **工具输出渐进裁剪** — opencode 在每次循环结束后裁剪旧工具输出（保护最近 40K），让 context 利用更高效。Cody 只有整体 compaction，没有针对工具输出的精细裁剪。

**建议：** 这三个都应该实现。特别是工具输出截断，对 SDK 用户来说是防止意外成本爆炸的重要保护。

---

### 4. 工具执行

| 维度 | Cody | opencode |
|------|------|----------|
| 并行调用 | 由 pydantic-ai 管理 | AI SDK 原生并行 + `batch` 工具（最多 25 个并行） |
| 错误处理 | `_with_model_retry` 允许 LLM 自纠错（最多 2 次重试） | `invalid` 工具兜底 + 工具名修复（大小写纠正） |
| 权限控制 | `PermissionManager` 审批 | 三级权限（allow/deny/ask）+ glob 模式 |

**Cody 优势：** `_with_model_retry` 机制让 LLM 看到工具错误后可以修正参数重试，这比 opencode 的 `invalid` 工具兜底更优雅。

**差距：** opencode 的 `batch` 工具允许 LLM 显式请求并行执行多个工具，Cody 没有等价机制。

**建议：** `batch` 工具可作为可选增强。

---

### 5. 结果质量保障

| 维度 | Cody | opencode |
|------|------|----------|
| LSP 诊断 | 有 `lsp_*` 工具，LLM 可主动调用 | 有 `lsp` 工具（实验性），类似 |
| 自动测试 | 无，依赖 LLM 主动 `exec_command` | 无，依赖 prompt 指导 LLM 跑测试 |
| 文件快照 | `FileHistory` undo/redo | `Snapshot.track()`/`Snapshot.patch()` git-based diff |
| Prompt 指导 | 简短（~21 行） | **按模型家族分别优化**的详细 prompt |

**关键差距：模型特定 Prompt**

opencode 为不同模型家族维护独立的 system prompt：
- `anthropic.txt` — 强调 TodoWrite、Task 工具、并行
- `beast.txt`（GPT-4 等）— 极度自主，"keep going until solved"
- `gemini.txt` — Gemini 特定优化
- `default.txt` — 精简版

**Cody 只有一套通用 prompt**，不区分模型。不同模型对 prompt 的响应差异很大，这会影响结果质量。

**建议：** 至少为 Claude 和 GPT 系列分别优化 prompt。这对结果质量提升很大且实现成本低。

---

### 6. 循环保护

| 维度 | Cody | opencode |
|------|------|----------|
| Token 限制 | ✅ `max_tokens`（默认 200K） | ❌ 无 |
| 成本限制 | ✅ `max_cost_usd`（默认 $5） | ❌ 无 |
| 循环检测 | ✅ 相似度检测（最近 6 轮，阈值 0.9） | ⚠️ Doom loop（连续 3 次相同工具+相同参数） |
| 步数限制 | ❌ 无 | ✅ `agent.steps`（可配置） |

**Cody 优势明显。** 熔断器（token + 成本 + 相似度）是 Cody 作为企业级 SDK 的重要安全网。opencode 在这方面相当薄弱——没有 token 限制、没有成本限制。

**差距：** 缺少步数限制。对 SDK 消费者来说，`max_steps` 是一个直观的控制旋钮。

**建议：** 在 `CircuitBreakerConfig` 中增加 `max_steps`。

---

### 7. 错误恢复 & 重试

| 维度 | Cody | opencode |
|------|------|----------|
| LLM API 重试 | ❌ 无 | ✅ 指数退避（2s×2^n，最大 30s），识别 rate limit/overloaded/5xx |
| Context overflow | 自动 compaction | 自动 compaction，失败则回退到重放早期消息 |
| 工具错误恢复 | `_with_model_retry`（2 次） | `invalid` 工具 + 工具名大小写修复 |

**关键差距：LLM API 重试**

这对 SDK 生产使用至关重要。LLM 提供商经常返回 429（rate limit）或 5xx（过载），没有自动重试意味着：
- 一个临时网络抖动就会导致整个 `run()` 失败
- SDK 消费者必须自己包装重试逻辑
- `CodyRateLimitError` 已定义但从未被抛出或处理

**建议：** P0 优先级。在 `runner.py` 或 model 层增加指数退避重试，至少覆盖 429 和 5xx。

---

### 8. 模型路由

| 维度 | Cody | opencode |
|------|------|----------|
| 模型解析 | `model_resolver.py` 只返回 `OpenAIChatModel` | Vercel AI SDK 支持 75+ Provider |
| 子 Agent 模型 | 与主 Agent 相同 | 可独立配置，`title` agent 用 small model |
| Small model | 无 | `Provider.getSmallModel()` 用于低成本操作 |

**差距：**
1. **Small model** — opencode 对 title 生成、摘要等低价值操作使用小模型省成本。Cody 对所有操作用同一个模型。
2. **子 Agent 独立模型** — opencode 允许每个 agent 配置不同模型，Cody 不支持。

**建议：** 增加 `small_model` 配置，用于 compaction/summary 等内部操作。子 Agent 独立模型也应支持。

---

## 二、SDK 可嵌入性审查

以下是从 **"业务方集成 Cody SDK"** 角度发现的核心问题：

### P0：阻塞性问题

#### 1. 无法注册自定义工具

`core/tools/registry.py` 的 `CORE_TOOLS` 是硬编码列表。SDK 消费者想添加自己的工具（如查数据库、调内部 API）只能：
- Fork 代码改 `CORE_TOOLS`（不可维护）
- 搭一个 MCP Server（太重）

**需要：** `builder.custom_tool(name, func, description)` API，让消费者用 Python 函数注册工具。

#### 2. 无法自定义 System Prompt

`runner.py:401-424` 的 persona 是硬编码字符串。SDK 消费者无法：
- 注入业务特定指令（"你是一个代码审查 Agent，只关注安全问题"）
- 替换默认 persona
- 在 prompt 中添加业务上下文

**需要：** `builder.system_prompt(text)` 或 `builder.prepend_prompt()` / `builder.append_prompt()`。

#### 3. 无 LLM API 重试

一次临时 429 或 5xx 就导致整个 `run()` 失败，对生产环境不可接受。

**需要：** 内置指数退避重试，至少覆盖 rate limit 和 server error。

### P1：重要问题

#### 4. 非流式 `run()` 不可取消

`client.py:589` 的 `run()` 没有 `cancel_event` 参数。一旦调用，无法中断。对生产系统来说，一个不可中断的 LLM 调用可能阻塞几分钟。

#### 5. 无 per-run 工具选择

Agent 在 `__init__` 时注册所有工具，之后无法变更。SDK 消费者无法说"这次 run 只允许读文件，不许执行命令"。

**需要：** `client.run(prompt, tools=["read_file", "grep"])` 或 `client.run(prompt, disabled_tools=["exec_command"])`。

#### 6. 无 step hook / 中间件

SDK 事件是 fire-and-forget 的观察机制。消费者无法：
- 在工具调用前审批/修改参数
- 在模型调用前修改 prompt
- 在工具返回后转换结果

**需要：** 拦截器模式——`builder.before_tool(callback)` / `builder.after_tool(callback)`。

#### 7. 存储层不可替换

`SessionStore`、`AuditLogger`、`FileHistory` 都是 SQLite 具体实现，无抽象接口。在 serverless/容器环境中，SQLite 可能不可用。消费者无法用 PostgreSQL/DynamoDB 替换。

**需要：** 抽象接口 + 默认 SQLite 实现，允许消费者注入自己的存储。

#### 8. 无工具输出截断

一个 `grep` 返回 10 万行结果会直接撑满上下文窗口，导致后续调用失败或成本暴涨。

**需要：** 自动截断 + 超长内容写入文件（参考 opencode 的 `Truncate.output()`）。

### P2：改进项

#### 9. `StreamChunk` 类型设计

当前是 flat 结构 + `type: str` 判别符。SDK 消费者需要写 `if chunk.type == "tool_call"` 这样的代码，类型安全差。应该用 discriminated union。

#### 10. Metrics 无界增长

`MetricsCollector._runs` 是无界列表。长时间运行的服务会内存泄漏。

#### 11. 无 stateless 模式

每次 `run()` 都创建 session 并持久化。对"发一个 prompt 拿结果就走"的场景是不必要的开销。

#### 12. `stream()` 不触发 SDK 事件

直接调 `stream()` 不会触发 `STREAM_START`/`TOOL_CALL` 等事件，只有 `run(stream=True)` 才会。这是 API 不一致。

---

## 三、优先级行动计划

### 立刻做（影响结果质量 + 生产稳定性）

| # | 项目 | 理由 | 难度 |
|---|------|------|------|
| 1 | **LLM API 重试** | 一个 429 就崩，生产不可用 | 低 |
| 2 | **工具输出截断** | 防止上下文爆炸，直接影响 Agent 成功率 | 低 |
| 3 | **结构化 Compaction 模板** | 用 Goal/Discoveries/Accomplished/Files 替代 "300 words"，保留更多关键信息 | 低 |
| 4 | **模型特定 Prompt** | 不同模型需要不同的指导策略 | 低 |
| 5 | **`max_steps` 熔断** | 简单直观的控制旋钮 | 低 |
| 6 | **Small model 配置** | Compaction/summary 用小模型省成本 | 低 |

### 尽快做（SDK 作为框架的核心能力）

| # | 项目 | 理由 | 难度 |
|---|------|------|------|
| 7 | **自定义工具注册 API** | 框架的核心价值——可扩展 | 中 |
| 8 | **System prompt 自定义** | 业务方必须能定制 Agent 行为 | 中 |
| 9 | **Per-run 工具选择** | 不同场景需要不同工具集 | 中 |
| 10 | **非流式 `run()` 可取消** | 生产环境必备 | 低 |

### 后续做（SDK 成熟度）

| # | 项目 | 理由 | 难度 |
|---|------|------|------|
| 11 | **Step hook / 中间件** | 高级消费者需要 | 高 |
| 12 | **存储层抽象** | serverless 部署需要 | 高 |
| 13 | **子 Agent 独立模型/权限** | 精细化控制 | 中 |
| 14 | **子 Agent 可恢复** | 长任务场景 | 中 |
| 15 | **StreamChunk 类型重构** | 类型安全 | 中 |

---

## 四、总结

**Cody 的 Agent 内核基础扎实，在循环保护（熔断器）和工具错误自纠方面甚至优于 opencode。**

但从 **"让 Agent 更稳定、更有效、结果更可用"** 的目标看，最大的短板是：

1. **稳定性：** 缺少 LLM API 重试 — 一个临时错误就全盘失败
2. **有效性：** 缺少工具输出截断和结构化 Compaction — 上下文利用效率低，Agent 容易"迷路"
3. **结果质量：** 缺少模型特定 Prompt — 同一套指令对不同模型效果差异大
4. **可嵌入性：** 缺少自定义工具和 Prompt — 业务方无法让 Agent 适配自己的场景

好消息是前 6 项（重试、截断、Compaction、Prompt、max_steps、small model）都是低难度高收益的改进，可以快速落地。

---

## 五、具体实现方案

### 方案 1：LLM API 重试（`runner.py`）

**现状：** `runner.py` 直接调用 `agent.run()` / `agent.run_stream()`，无任何重试。
`CodyRateLimitError` 在 `core/__init__.py` 中定义但从未使用。

**改法：** 在 `runner.py` 的 `run()` 和 `stream()` 中包装重试逻辑。

```python
# core/retry.py（新文件）

import asyncio
import logging
from typing import TypeVar, Callable, Awaitable

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}

# 可重试的错误关键词（pydantic-ai / httpx 抛出的异常信息）
_RETRYABLE_KEYWORDS = ("rate limit", "overloaded", "too many requests", "server error", "connection")


def _is_retryable(exc: Exception) -> bool:
    """判断异常是否可重试。"""
    msg = str(exc).lower()
    # 检查状态码
    for code in _RETRYABLE_STATUS_CODES:
        if str(code) in msg:
            return True
    # 检查关键词
    return any(kw in msg for kw in _RETRYABLE_KEYWORDS)


async def with_retry(
    fn: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    **kwargs,
) -> T:
    """带指数退避的重试包装器。

    仅对 rate limit (429) 和 server error (5xx) 重试。
    对参数错误 (4xx) 和 context overflow 不重试（让上层处理）。
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries or not _is_retryable(exc):
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1, max_retries, delay, exc,
            )
            await asyncio.sleep(delay)
    raise last_exc  # unreachable, but satisfies type checker
```

**集成点：** 在 `runner.py` 的 `run()` 方法中：
```python
# 现在：
result = await agent.run(prompt, message_history=history, deps=deps)

# 改为：
from .retry import with_retry
result = await with_retry(agent.run, prompt, message_history=history, deps=deps)
```

---

### 方案 2：工具输出截断（`core/tools/` 装饰器）

**现状：** 每个工具直接返回 `str`，无长度限制。`grep` 虽有 `max_matches=200`，但 200 个匹配行仍可能很长。`read_file` 没有上限。`exec_command` 返回完整 stdout。

**改法：** 在工具注册层统一截断。

```python
# core/tools/truncate.py（新文件）

import tempfile
from pathlib import Path

# 工具输出的 token 上限（约 30K tokens ≈ 120K chars）
MAX_OUTPUT_TOKENS = 30_000
MAX_OUTPUT_CHARS = MAX_OUTPUT_TOKENS * 4  # 粗估


def truncate_output(output: str, tool_name: str = "") -> str:
    """截断工具输出。超长部分写入临时文件，返回截断内容 + 文件路径。"""
    if len(output) <= MAX_OUTPUT_CHARS:
        return output

    # 写入临时文件
    suffix = f".{tool_name}.txt" if tool_name else ".tool_output.txt"
    fd = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, prefix="cody_", delete=False
    )
    fd.write(output)
    fd.close()
    path = fd.name

    # 返回截断内容 + 提示
    truncated = output[:MAX_OUTPUT_CHARS]
    return (
        f"{truncated}\n\n"
        f"... [OUTPUT TRUNCATED — {len(output):,} chars total, "
        f"showing first {MAX_OUTPUT_CHARS:,}]\n"
        f"Full output saved to: {path}\n"
        f"Use read_file('{path}') to read specific sections if needed."
    )
```

**集成点：** 在 `core/tools/registry.py` 的 `register_tools()` 中包装每个工具的返回值。或更简单——在每个工具函数末尾调用 `truncate_output()`。

推荐在 `grep`、`read_file`、`exec_command`、`glob` 四个高风险工具中优先加。

---

### 方案 3：结构化 Compaction 模板

**现状（`context.py:114-126`）：**
```python
_SUMMARIZATION_PROMPT = """
You are a conversation summarizer for an AI coding assistant.
Summarize the conversation below. Preserve:
- User goals and intent
- Key decisions made
- File paths and code locations mentioned
- Tool results (especially errors and warnings)
- Constraints or requirements stated
Format: bullet points, 300 words or fewer. Do NOT include code blocks unless they contain critical one-liners.
"""
```

问题：太泛，LLM 会丢掉关键上下文（如当前在哪个文件的哪一行工作）。

**改为（参考 opencode 的结构化模板）：**
```python
_SUMMARIZATION_PROMPT = """\
You are summarizing a conversation between a user and an AI coding assistant.

Output your summary using EXACTLY this structure:

## Goal
What the user is trying to accomplish (1-2 sentences).

## Key Instructions
Constraints, preferences, or requirements the user stated (bullet points).

## What Was Done
Actions already completed, with specific outcomes (bullet points with file paths).

## Current State
Where things stand right now — what's working, what's not, any errors encountered.

## Relevant Files
File paths that are actively being worked on or referenced, with brief notes:
- `path/to/file.py` — modified: added X function
- `path/to/test.py` — created: tests for X

## Open Items
Anything still pending or unresolved.

Be specific. Include file paths, function names, line numbers, error messages.
Do NOT include code blocks. Keep total length under 500 words.
"""
```

**核心差异：**
- 固定结构 → LLM 不会遗漏关键类别
- "Relevant Files" 带状态注释 → Agent 恢复后知道哪些文件改过/创建过
- "Current State" → Agent 恢复后知道上次停在哪里
- "Open Items" → Agent 知道接下来该做什么
- 500 words 而非 300 → 对长对话 300 太短

---

### 方案 4：模型特定 Prompt

**现状（`runner.py:402-424`）：** 一套 21 行的通用 prompt，不区分模型。

**改法：** 在 `runner.py` 的 `_build_agent()` 中根据模型名称选择 prompt 变体。

```python
# core/prompts.py（新文件）

# 所有模型共享的基础段落
_BASE = (
    "You are Cody, an AI coding assistant. "
    "You have access to file operations, shell commands, skills, web search, "
    "and code intelligence via LSP. "
    "When a skill matches the task, call read_skill(skill_name) to load its full instructions. "
    "Use webfetch/websearch for web lookups and lsp_* tools for code intelligence. "
    "Always execute commands and file operations as needed to complete tasks."
)

_SUB_AGENT_GUIDANCE = (
    "## Sub-Agent Parallelism\n"
    "You SHOULD use spawn_agent() when the task involves 2 or more independent "
    "sub-tasks. Doing work in parallel is faster and preferred over doing it "
    "sequentially. Spawn multiple agents in a single tool-call turn.\n\n"
    "Examples of when to spawn agents:\n"
    "  - User: 'Add unit tests for auth, billing, and notification modules'\n"
    "    → spawn 3 test agents, one per module\n"
    "  - User: 'Refactor logging in src/api/ and src/workers/'\n"
    "    → spawn 2 code agents, one per directory\n"
    "  - User: 'Analyze the architecture of frontend and backend'\n"
    "    → spawn 2 research agents in parallel\n\n"
    "Only skip sub-agents when: the task is truly single-step, or steps have "
    "sequential dependencies (step B needs output of step A)."
)

# Claude 系列专用指导
_CLAUDE_SPECIFIC = (
    "## Working Style\n"
    "- Keep responses concise. Lead with the action, not the reasoning.\n"
    "- When modifying code, read the file first, then edit. Never guess file contents.\n"
    "- After making changes, verify by running tests or checking with LSP diagnostics.\n"
    "- If a tool call fails, analyze the error and try a different approach "
    "rather than retrying the same call.\n"
    "- When the task is complete, provide a brief summary of what was done.\n\n"

    "## Tool Usage\n"
    "- Prefer grep/glob for file discovery over listing directories.\n"
    "- Use exec_command for running tests, builds, and git operations.\n"
    "- For large codebases, spawn a research sub-agent to explore before modifying.\n"
    "- Read relevant files before editing — never assume content.\n"
    "- When multiple independent tool calls are needed, make them all in a single turn."
)

# GPT/OpenAI 系列专用指导
_GPT_SPECIFIC = (
    "## Working Style\n"
    "- You are an autonomous coding agent. Keep working until the task is fully complete.\n"
    "- Do NOT ask the user for confirmation at intermediate steps. Just do the work.\n"
    "- After making changes, ALWAYS verify by running tests or the build.\n"
    "- If tests fail, fix the issue and re-run. Do not stop until tests pass.\n"
    "- If you are unsure about something, read more code to understand before acting.\n\n"

    "## Tool Usage\n"
    "- Read the file BEFORE editing. Never assume file contents.\n"
    "- Use grep to find relevant code across the codebase.\n"
    "- Use exec_command to run tests, builds, and linters.\n"
    "- When you encounter an error, analyze it and try a different approach."
)

# Gemini 系列专用指导
_GEMINI_SPECIFIC = (
    "## Working Style\n"
    "- Be thorough and systematic. Read relevant files before making changes.\n"
    "- After editing code, verify the changes work by running tests.\n"
    "- If a tool call fails, try an alternative approach.\n"
    "- Provide a clear summary when the task is complete.\n\n"

    "## Tool Usage\n"
    "- Use grep and glob for codebase exploration.\n"
    "- Use exec_command for running tests, builds, and other commands.\n"
    "- Read files before editing to understand existing code."
)

# 默认/其他模型
_DEFAULT_SPECIFIC = (
    "## Working Style\n"
    "- Read files before editing. Verify changes work by running tests.\n"
    "- If a tool call fails, analyze the error and try a different approach.\n"
    "- Keep responses short and focused on the task."
)


def get_persona(model_name: str) -> str:
    """根据模型名称返回优化的 system prompt。"""
    model_lower = model_name.lower()

    if "claude" in model_lower or "anthropic" in model_lower:
        specific = _CLAUDE_SPECIFIC
    elif "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower or "o4" in model_lower:
        specific = _GPT_SPECIFIC
    elif "gemini" in model_lower:
        specific = _GEMINI_SPECIFIC
    else:
        specific = _DEFAULT_SPECIFIC

    return f"{_BASE}\n\n{_SUB_AGENT_GUIDANCE}\n\n{specific}"
```

**集成点：** `runner.py:402` 改为：
```python
from .prompts import get_persona
system_parts = [get_persona(self.config.model)]
```

**核心差异解释：**

| 模型 | 关键差异 | 原因 |
|------|---------|------|
| Claude | 强调并行工具调用、简洁回复、先读后改 | Claude 擅长并行工具调用，但默认回复偏长 |
| GPT | 强调自主执行、不要中间确认、测试必须通过 | GPT 系列倾向在中间停下来问用户，需要推它继续 |
| Gemini | 强调系统性、先读后改 | Gemini 有时会跳过读文件直接编辑 |
| 默认 | 最精简，只给核心规则 | 未知模型不宜给太多特定指导 |

---

### 方案 5：`max_steps` 熔断

**现状：** `CircuitBreakerConfig` 有 `max_tokens`、`max_cost_usd`、`loop_detect_turns`，但没有步数限制。

**改法：**

```python
# config.py — CircuitBreakerConfig 增加字段
class CircuitBreakerConfig(BaseModel):
    enabled: bool = True
    max_tokens: int = 200_000
    max_cost_usd: float = 5.0
    max_steps: int = 50          # 新增：最大工具调用步数，0=无限制
    loop_detect_turns: int = 6
    loop_similarity_threshold: float = 0.9
    model_prices: dict[str, float] = Field(default_factory=lambda: {
        "default": 0.000003,
    })
```

**集成点：** `runner.py` 的 `_check_circuit_breaker()` 增加步数检查。

---

### 方案 6：Small Model 配置

**现状：** `CompactionConfig` 已支持独立 `model`，但没有通用的 "small model" 概念。

**改法：**

```python
# config.py — Config 增加字段
class Config(BaseModel):
    model: str = ''
    model_base_url: Optional[str] = None
    model_api_key: Optional[str] = None
    small_model: Optional[str] = None      # 新增：低成本操作用的小模型
    small_model_base_url: Optional[str] = None
    small_model_api_key: Optional[str] = None
    # ... 其他字段不变
```

**使用场景：**
- Compaction（如果 `compaction.model` 未设置，自动用 `small_model`）
- 子 Agent（research 类型可以用 small model）
- 未来：session 标题生成

---

### 实现优先级建议

以上 6 个方案按**实现顺序**排列（考虑依赖关系和收益）：

1. **Prompt 优化（方案 4）**— 零风险，立即提升结果质量，不改任何逻辑
2. **Compaction 模板（方案 3）**— 零风险，替换一个字符串常量
3. **工具输出截断（方案 2）**— 低风险，防止 context 爆炸
4. **LLM API 重试（方案 1）**— 中风险，需要测试重试逻辑
5. **max_steps 熔断（方案 5）**— 低风险，加一个配置字段 + 一个条件检查
6. **Small model（方案 6）**— 低风险，加配置字段 + 修改 model resolver 的 fallback
