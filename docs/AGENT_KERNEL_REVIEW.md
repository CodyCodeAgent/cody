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
| Compaction 触发 | ~~接近 token 限制时自动触发~~ ✅ 支持固定阈值 + `trigger_ratio` 百分比触发 | 每步后检查：`token >= input_limit - reserved` |
| 策略 | ~~截断 + LLM 摘要（两种可选）~~ ✅ 三阶段：选择性修剪 → 截断 → LLM 结构化摘要 | LLM 摘要（结构化模板：Goal/Instructions/Discoveries/Accomplished/Files） |
| 工具输出裁剪 | ~~无~~ ✅ **已实现**：Selective Pruning，保护最近 40K tokens，旧工具输出替换为 `[output pruned]` | **有**：保护最近 40K tokens 的工具输出，旧的标记为 compacted |
| 工具输出截断 | 无 | **有**：每个工具输出自动截断，超长内容写入临时文件返回路径 |
| Compaction 后恢复 | 替换历史消息 | 注入合成用户消息 "Continue if you have next steps" 自动恢复 |
| 摘要 Prompt | ✅ 结构化模板（Goal/Instructions/Discoveries/Progress/Files/Decisions）+ handoff 视角 + 安全指令 | 结构化模板（Goal/Instructions/Discoveries/Accomplished/Files） |
| 保留最近消息 | ✅ 固定条数 + token 预算（`keep_recent_tokens`）双模式 | 保留最后 N turns |

**关键差距：**

1. **工具输出截断（Tool Output Truncation）**— 这是 opencode 的一个重要设计。每个工具的返回值都经过自动截断处理，超长输出写入临时文件。Cody 没有这个机制，一个 `grep` 返回大量结果时会直接撑爆上下文。

2. ~~**结构化 Compaction 模板** — opencode 的 compaction prompt 要求按固定结构输出（Goal/Instructions/Discoveries/Accomplished/Relevant Files），这比 Cody 的 "300 words or fewer" 泛化摘要能保留更多关键信息。~~ ✅ **已完成** — 实现了结构化摘要模板（Goal/Instructions/Discoveries/Progress/Files/Decisions），含 handoff 视角、安全指令、plan/spec 保留引导、目录支持、精确值保留。对比 OpenCode 的模板，我们额外做了：安全指令（防 prompt injection）、增量合并指引、空 section 省略、`max_summary_tokens` API 层限制。

3. ~~**工具输出渐进裁剪** — opencode 在每次循环结束后裁剪旧工具输出（保护最近 40K），让 context 利用更高效。Cody 只有整体 compaction，没有针对工具输出的精细裁剪。~~ ✅ **已完成** — 实现了 Selective Pruning（`prune_tool_outputs()`），保护最近 40K tokens，最低节省 20K tokens，旧工具输出替换为 `[output pruned at <ts>]` 标记。参数可通过 `CompactionConfig` 配置。

**建议：** 工具输出截断（单条工具返回值的长度限制）仍需实现，对 SDK 用户来说是防止意外成本爆炸的重要保护。

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
| LLM API 重试 | ~~❌ 无~~ ✅ 指数退避（2s×2^n，最大 30s），覆盖 429/5xx，`run()` + `run_sync()` | ✅ 指数退避（2s×2^n，最大 30s），识别 rate limit/overloaded/5xx |
| Context overflow | 自动 compaction | 自动 compaction，失败则回退到重放早期消息 |
| 工具错误恢复 | `_with_model_retry`（2 次） | `invalid` 工具 + 工具名大小写修复 |

~~**关键差距：LLM API 重试**~~ ✅ **已完成**

实现了 `core/retry.py` 模块，`run()` 和 `run_sync()` 自动对 429/5xx 指数退避重试。对 context overflow、auth 错误等非暂态错误不重试（fail fast）。配置项：`retry.enabled`（默认开启）、`retry.max_retries`（3）、`retry.base_delay`（2.0s）、`retry.max_delay`（30s）。`run_stream()` 暂不支持自动重试（流式上下文管理器难以安全重试）。

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

#### ~~3. 无 LLM API 重试~~ ✅ 已完成

~~一次临时 429 或 5xx 就导致整个 `run()` 失败，对生产环境不可接受。~~

已实现：`core/retry.py` + `Config.retry`（RetryConfig），`run()` 和 `run_sync()` 自动重试 429/5xx。

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

| # | 项目 | 理由 | 难度 | 状态 |
|---|------|------|------|------|
| 1 | ~~**LLM API 重试**~~ | ~~一个 429 就崩，生产不可用~~ | ~~低~~ | ✅ 已完成 |
| 2 | **工具输出截断** | 防止上下文爆炸，直接影响 Agent 成功率 | 低 | 待做 |
| 3 | ~~**结构化 Compaction 模板**~~ | ~~用 Goal/Discoveries/Accomplished/Files 替代 "300 words"，保留更多关键信息~~ | ~~低~~ | ✅ 已完成 |
| 4 | **模型特定 Prompt** | 不同模型需要不同的指导策略 | 低 | 已决定不做 |
| 5 | **`max_steps` 熔断** | 简单直观的控制旋钮 | 低 | 待做 |
| 6 | **Small model 配置** | Compaction/summary 用小模型省成本 | 低 | 待做 |

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

1. ~~**稳定性：** 缺少 LLM API 重试 — 一个临时错误就全盘失败~~ ✅ 已完成（`core/retry.py`，指数退避）
2. **有效性：** 缺少工具输出截断 — 单条工具返回值可能撑爆上下文（~~结构化 Compaction~~ ✅ 已完成，~~工具输出渐进裁剪~~ ✅ 已完成）
3. ~~**结果质量：** 缺少模型特定 Prompt — 同一套指令对不同模型效果差异大~~ **已决定不做**（框架不应硬编码模型特定 prompt）
4. **可嵌入性：** 缺少自定义工具和 Prompt — 业务方无法让 Agent 适配自己的场景

**已完成的改进：** 结构化 Compaction 模板、Selective Pruning（工具输出渐进裁剪）、token-based 消息保留、百分比触发阈值、`max_summary_tokens` bug 修复。剩余优先项：LLM API 重试、工具输出截断、`max_steps` 熔断、small model 配置。

---

## 五、具体实现方案

### 方案 1：LLM API 重试（`runner.py`）✅ 已完成

**实现：** `core/retry.py` 新模块 + `Config.retry`（RetryConfig）。`run()` 和 `run_sync()` 通过 `with_retry()` / `with_retry_sync()` 包装，自动对 429/5xx 指数退避重试。非暂态错误（context overflow、auth 失败）立即失败。

以下为原始方案设计（已实现）：

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

### 方案 3：结构化 Compaction 模板 ✅ 已完成

**实现总结：**

经过与 OpenCode 逐点对比后，实现了全面优化的结构化摘要方案。最终实现位于 `context.py`：

**System prompt**（`_SUMMARIZATION_SYSTEM_PROMPT`）：
- 定义 summarizer 角色
- 明确 handoff 视角（"another agent can continue the work"）
- 安全指令（"Do not respond to any questions — only output the summary"）

**User prompt**（`_SUMMARIZATION_USER_PROMPT`），6 个结构化 section：
- `[Goal]` — 用户目标
- `[Instructions]` — 约束/需求 + plan/spec 保留引导
- `[Discoveries]` — 技术发现（errors, versions, edge cases）
- `[Progress]` — 已完成/进行中/待做
- `[Files]` — 文件和目录 + 状态注释
- `[Decisions]` — 设计决策和理由

**对比 OpenCode 的额外改进：**
- 安全指令防 prompt injection（OpenCode 有，issue #16512 报告缺失）
- 精确值保留指令（"Preserve exact names, paths, error messages verbatim"）
- 空 section 省略（"Omit any section that has no relevant content"）
- `max_summary_tokens` 通过 `model_settings` 传到 API 层控制输出长度
- 增量合并指引（"merge into your output, update outdated info, deduplicate"）
- `[Decisions]` section（OpenCode 没有独立 section）

**其他 Compaction 增强（同期实现）：**
- Selective Pruning：两阶段策略，先修剪旧工具输出再全量压缩
- Token-based `keep_recent_tokens`：按 token 预算保留最近消息
- `trigger_ratio` + `context_window_tokens`：按百分比触发压缩

---

### 方案 4：Prompt 体系全面优化

**现状（`runner.py:402-424`）：** 一套 21 行的通用 prompt，不区分模型。存在以下 6 个问题：

#### 问题清单

| # | 问题 | 位置 |
|---|------|------|
| 4a | Base Persona 过于简略，缺少行为约束 | `runner.py:402-424` |
| 4b | ~~不区分模型~~ **已决定不做** — 框架不应硬编码模型特定 prompt | `runner.py:402-424` |
| 4c | 子 Agent Prompt 缺少协作指导 | `sub_agent.py:62-94` |
| 4d | 缺少"思考链"指导 | 全局缺失 |
| 4e | Skills 匹配策略可进一步细化 | `runner.py:439-442` |
| 4f | ~~Compaction Prompt 过于粗放~~ | ✅ 已在方案 3 实现：结构化模板 + handoff + 安全指令 |

#### 问题 4a：Base Persona 过于简略

当前 21 行 prompt 缺少以下关键行为约束：

- **输出格式规范** — 何时使用 Markdown、代码块、列表
- **错误处理指导** — 工具调用失败时的重试策略和降级方案
- **安全约束** — 明确禁止的操作（如删除根目录、修改系统文件）
- **代码质量要求** — 保持现有代码风格、不引入不必要的依赖
- **任务完成标准** — 什么算"完成"（测试通过？编译成功？）
- **上下文管理** — 指导 Agent 在长对话中主动使用 `save_memory`

建议 prompt 结构：
```
1. 角色定义（你是谁）
2. 能力边界（你能/不能做什么）
3. 行为准则（怎么做）
4. 输出规范（怎么表达）
5. 安全约束（什么不能做）
6. 工具使用指南（优先级和策略）
```

#### ~~问题 4b：不区分模型~~（已决定不做）

理由：Cody 是框架，不应对特定模型做硬编码的 prompt hack；维护成本高；好的 prompt 应该是模型无关的。

#### 问题 4c：子 Agent Prompt 缺少协作指导

**现状（`sub_agent.py:62-94`）：** 子 Agent 只知道自己的职责，不知道如何与主 Agent 交互。

缺少：
- **输出格式要求** — 结构化摘要，方便主 Agent 聚合多个子 Agent 结果
- **错误上报规范** — 什么情况下提前终止并报告（而不是无限重试）
- **范围约束** — 明确不要超出指定目录/文件范围

#### 问题 4d：缺少"思考链"指导

当前 prompt 没有引导 Agent 先思考再行动：
- 处理复杂任务时，先制定计划再执行
- 修改代码前，先阅读相关代码理解上下文
- 运行命令前，先检查当前环境状态

#### 问题 4e：Skills 匹配策略可进一步细化

**现状：** Prompt 只说 "When a skill matches the task, call read_skill()"，可以更精细：
- 基于文件类型/项目特征的自动触发建议（检测到 Dockerfile → 提示 docker skill）
- Skill 之间的优先级/冲突处理规则
- 明确何时**不应该**加载 skill（避免不必要的 context 占用）

---

#### 完整实现方案

新建 `core/prompts.py`，包含所有 prompt 逻辑：

```python
# core/prompts.py（新文件）

# ── 所有模型共享的基础段落 ──────────────────────────────────────────────

_BASE = (
    "You are Cody, an AI coding assistant.\n\n"

    "## Capabilities\n"
    "You have access to: file operations (read/write/edit), shell commands, "
    "skills, web search, code intelligence via LSP, and sub-agent spawning. "
    "When a skill matches the task, call read_skill(skill_name) to load its "
    "full instructions. "
    "Use webfetch/websearch for web lookups and lsp_* tools for code intelligence.\n\n"

    "## Boundaries\n"
    "- NEVER delete files outside the project directory without explicit user confirmation.\n"
    "- NEVER modify system files (/etc, /usr, ~/.bashrc, etc.).\n"
    "- NEVER run destructive commands (rm -rf /, DROP DATABASE, etc.) without confirmation.\n"
    "- If unsure whether an action is safe, ask the user.\n\n"

    "## Output Format\n"
    "- Use Markdown for structured responses. Use code blocks with language tags.\n"
    "- Keep explanations concise — lead with the action or answer, not the reasoning.\n"
    "- When reporting completed work, provide a brief structured summary:\n"
    "  what was changed, which files, and how to verify.\n\n"

    "## Code Quality\n"
    "- Match existing code style (indentation, naming conventions, patterns).\n"
    "- Do not introduce unnecessary dependencies.\n"
    "- Do not refactor unrelated code unless explicitly asked.\n\n"

    "## Task Completion\n"
    "- A task is 'done' when: the change works (tests pass or manual verification), "
    "and the user's request is fully addressed.\n"
    "- After making changes, verify by running tests, the build, or LSP diagnostics.\n"
    "- If verification fails, fix the issue before reporting completion.\n\n"

    "## Context Management\n"
    "- In long conversations, use save_memory() to persist important discoveries "
    "(project patterns, build commands, test conventions) for future sessions.\n"
    "- When tool output is very large, focus on the relevant portion rather than "
    "processing the entire output.\n"
)

# ── 子 Agent 并行指导 ─────────────────────────────────────────────────

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

# ── 思考链指导 ────────────────────────────────────────────────────────

_THINKING_GUIDANCE = (
    "## Approach\n"
    "For complex tasks, follow this order:\n"
    "1. **Understand** — Read relevant files and understand the existing code before changing it.\n"
    "2. **Plan** — For multi-step tasks, outline the steps before executing.\n"
    "3. **Execute** — Make changes one logical step at a time.\n"
    "4. **Verify** — Run tests or check results after each significant change.\n"
    "5. **Report** — Summarize what was done and any remaining issues.\n\n"
    "Do NOT skip step 1. Reading first prevents wasted effort from incorrect assumptions."
)

# ── Skills 匹配指导 ──────────────────────────────────────────────────

_SKILLS_GUIDANCE = (
    "## Skills Usage\n"
    "- When a skill matches the user's task, call read_skill(skill_name) to load it.\n"
    "- Context clues for skill selection: file types in the project (Dockerfile → docker skill), "
    "task keywords ('deploy' → deployment skill), project config files.\n"
    "- Do NOT load multiple skills at once unless the task explicitly requires combining them "
    "— each skill adds context overhead.\n"
    "- If the task is simple (single file edit, quick grep), skip skills entirely.\n"
)

def build_system_prompt() -> str:
    """构建统一的 system prompt（模型无关）。

    Prompt 结构：
      1. 角色定义 + 能力边界 + 安全约束（_BASE）
      2. 思考链指导（_THINKING_GUIDANCE）
      3. 子 Agent 并行指导（_SUB_AGENT_GUIDANCE）
      4. Skills 使用指导（_SKILLS_GUIDANCE）

    注意：不做模型区分。框架不应硬编码模型特定的 prompt hack。
    """
    return "\n\n".join([
        _BASE,
        _THINKING_GUIDANCE,
        _SUB_AGENT_GUIDANCE,
        _SKILLS_GUIDANCE,
    ])
```

#### 子 Agent Prompt 优化

同时优化 `sub_agent.py` 中的 `_AGENT_PROMPTS`，增加协作指导：

```python
# sub_agent.py — 替换 _AGENT_PROMPTS

_AGENT_PROMPTS = {
    AgentType.CODE: (
        "You are a coding sub-agent spawned to handle a specific task. "
        "You have access to: file read/write/edit, directory listing, "
        "grep/glob/search, and shell command execution.\n\n"
        "## Rules\n"
        "- Focus exclusively on the task described in the prompt.\n"
        "- Only modify files directly related to the task — do not touch unrelated code.\n"
        "- Stay within the directories/files specified. If the task says 'in src/auth/', "
        "do not modify files outside that path.\n"
        "- Read files before editing to understand existing code.\n\n"
        "## Error Handling\n"
        "- If you encounter a blocking error you cannot resolve after 2 attempts, "
        "stop and report the error clearly instead of retrying indefinitely.\n"
        "- Include the error message and what you tried.\n\n"
        "## Output Format\n"
        "When done, provide a structured summary:\n"
        "- **Changed files**: list of files modified/created with one-line descriptions\n"
        "- **What was done**: brief description of the changes\n"
        "- **Verification**: test results or how to verify the changes\n"
        "- **Issues**: any problems encountered or remaining concerns"
    ),
    AgentType.RESEARCH: (
        "You are a research sub-agent spawned to analyze code. "
        "You have access to: file reading, directory listing, and "
        "grep/glob/search. You CANNOT modify files or run commands.\n\n"
        "## Rules\n"
        "- Provide thorough, structured analysis with specific file paths "
        "and line references.\n"
        "- Stay focused on the research question — do not go on tangents.\n\n"
        "## Error Handling\n"
        "- If a file or pattern is not found, note it and try alternative approaches "
        "(different search terms, related filenames) before giving up.\n\n"
        "## Output Format\n"
        "When done, provide a structured summary:\n"
        "- **Key findings**: bullet points with file:line references\n"
        "- **Architecture/patterns observed**: relevant design patterns found\n"
        "- **Relevant files**: list of files examined, with brief role descriptions\n"
        "- **Unanswered questions**: anything you could not determine"
    ),
    AgentType.TEST: (
        "You are a testing sub-agent spawned to write and run tests. "
        "You have access to: file read/write/edit, directory listing, "
        "grep/glob, and shell command execution.\n\n"
        "## Rules\n"
        "- Write focused tests for the specified functionality.\n"
        "- Follow existing test patterns in the project (framework, naming, structure).\n"
        "- Run the tests after writing them.\n\n"
        "## Error Handling\n"
        "- If tests fail, attempt to fix them (up to 2 iterations).\n"
        "- If you cannot make tests pass, report the failures clearly.\n\n"
        "## Output Format\n"
        "When done, provide a structured summary:\n"
        "- **Tests written**: list of test files/functions created\n"
        "- **Results**: pass/fail counts with details on any failures\n"
        "- **Coverage**: what scenarios are covered and what is not\n"
        "- **Issues**: any problems encountered"
    ),
    AgentType.GENERIC: (
        "You are a sub-agent spawned to handle a specific task. "
        "You have access to: file read/write/edit, directory listing, "
        "grep/glob/search, and shell command execution.\n\n"
        "## Rules\n"
        "- Focus exclusively on the task described in the prompt.\n"
        "- Stay within scope — do not modify unrelated files.\n\n"
        "## Error Handling\n"
        "- If you encounter a blocking error after 2 attempts, stop and report.\n\n"
        "## Output Format\n"
        "When done, provide a structured summary:\n"
        "- **What was done**: brief description\n"
        "- **Files affected**: list with one-line descriptions\n"
        "- **Issues**: any problems or remaining concerns"
    ),
}
```

#### 集成点

`runner.py:402` 改为：
```python
from .prompts import build_system_prompt
system_parts = [build_system_prompt()]
```

#### 新旧 Prompt 对比

| 维度 | 旧 Prompt（21 行） | 新 Prompt |
|------|-------------------|-----------|
| 角色定义 | ✅ 有 | ✅ 有，更完整 |
| 能力边界 | ❌ 无 | ✅ 有（Capabilities + Boundaries） |
| 安全约束 | ❌ 无 | ✅ 有（禁止删除根目录、修改系统文件） |
| 输出格式 | ❌ 无 | ✅ 有（Markdown 规范 + 完成报告格式） |
| 代码质量 | ❌ 无 | ✅ 有（匹配风格、不引入多余依赖） |
| 任务完成标准 | ❌ 无 | ✅ 有（测试通过 = 完成） |
| 思考链 | ❌ 无 | ✅ 有（Understand → Plan → Execute → Verify → Report） |
| 上下文管理 | ❌ 无 | ✅ 有（save_memory 指导） |
| 子 Agent 并行 | ✅ 有 | ✅ 保留 |
| Skills 指导 | ⚠️ 一句话 | ✅ 详细（上下文线索、不要过度加载） |
| 模型区分 | ❌ 无 | ❌ 不做（框架不应硬编码模型特定 prompt） |
| 子 Agent 协作 | ❌ 无 | ✅ 结构化输出格式 + 错误上报 + 范围约束 |

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
