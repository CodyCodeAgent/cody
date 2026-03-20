# Cody — Harness 能力补齐需求文档

**单 Agent 场景 · 基于 Harness 方法论**

| 字段 | 内容 |
|------|------|
| 文档版本 | v1.0 |
| 日期 | 2026-03-20 |
| 分析基础 | Cody v1.7.3（CodyCodeAgent/cody@main） |
| 目标场景 | 单 Agent 可靠运行，不涉及多 Agent 编排 |
| 文档状态 | 待评审 |

---

## 1. 背景与目标

Harness 方法论是 2025-2026 年间 AI 工程领域涌现的核心工程实践框架，核心思想是：

> **模型负责智能，Harness 负责可靠性。**

Cody 在开发时这套方法论尚未成型，因此在单 Agent 可靠性的几个关键维度存在缺口。本文档基于对 Cody 源码的逐文件分析，对照 Harness 方法论五大支柱，梳理出需要补齐的能力，并给出具体的需求定义和实现指导。

本次补齐**聚焦单 Agent 场景**，不涉及多 Agent 编排（StageGraph、多角色流水线等）。

---

## 2. 现状分析

### 2.1 已有能力（不需要动）

以下能力 Cody 已有完整实现，本次不涉及：

| 模块 | 文件 | 说明 |
|------|------|------|
| 边界控制基础 | `permissions.py` | allow/deny/confirm 三级权限，工具白名单，路径遍历保护 |
| 上下文注入 | `project_instructions.py` | CODY.md 静态读取，全局+项目两级 |
| 技能管理 | `skill_manager.py` | 11 个内置技能，三层优先级，XML 注入 prompt |
| 会话持久化 | `session.py` | SQLite，compaction checkpoint，多轮对话 |
| 上下文压缩 | `context.py` | 截断压缩 + LLM 语义压缩两种模式 |
| 子 Agent 雏形 | `sub_agent.py` | asyncio 并发孵化，5 种 agent 类型，semaphore 限流 |
| 审计日志 | `audit.py` | SQLite 写入，tool_call/file_write 等事件类型 |
| MCP 集成 | `mcp_client.py` | stdio JSON-RPC，动态 prompt 注入 |
| LSP 集成 | `lsp_client.py` | pyright/tsserver，代码诊断/跳转/引用 |
| 流式输出 | `runner.py` | StreamEvent union type，TextDelta/ToolCall/Done |

### 2.2 缺口分析

对照 Harness 方法论五大支柱，存在以下明显缺口：

| Harness 支柱 | 缺口描述 | 风险 | 单 Agent 必需 | 本次 |
|-------------|---------|------|-------------|------|
| 边界控制 | 无 token/cost 熔断，任务失控无法自动止损 | 长任务烧光预算 | 是 | ✅ 补齐 |
| 上下文工程 | 无跨任务记忆，每次任务从零开始；上下文为静态注入 | 重复犯同样错误，无法积累经验 | 是 | ✅ 补齐 |
| 人工介入 | confirm 下放 shell 层，无标准化反馈回路；AI 无置信度自评 | 人工反馈无法结构化注入下次执行 | 是 | ✅ 补齐 |
| 编排协调 | SubAgentManager 仅动态孵化，无预设流水线 | 多 Agent 场景不在本次范围 | 否 | ⏭ 跳过 |
| 止损观测 | AuditLogger 只写入不分析，无异常检测，无死循环识别 | 问题出现后无法及时发现 | 是 | ✅ 部分补齐 |

---

## 3. 需求详述

### 3.1 CircuitBreaker — 止损熔断

#### 背景

目前 Cody 没有任何 token 或成本的自动止损机制。一个写错的任务描述或者 AI 进入死循环，会持续消耗 token 直到用户手动中断，在生产环境和 SDK 嵌入场景里不可接受。

#### 需求列表

| 编号 | 功能点 | 描述 | 优先级 | 改动范围 |
|------|--------|------|--------|---------|
| CB-01 | Token 熔断 | 在 runner.py 的执行循环中累计当次任务消耗的 token 数，超过配置阈值时抛出 `CircuitBreakerError` 中断执行，在 CodyResult 中记录熔断原因 | P0 | `runner.py` / `config.py` |
| CB-02 | Cost 熔断 | 支持按估算成本（token × 单价）熔断，不同模型单价可在 config 中配置 | P1 | `runner.py` / `config.py` |
| CB-03 | 死循环检测 | 检测连续 N 次 tool call 的输出内容相似度超过阈值（如 90%），判定为死循环并熔断 | P1 | `runner.py` |
| CB-04 | 熔断事件 | 熔断时产出 `CircuitBreakerEvent`，集成进现有 `StreamEvent` union type，让调用方可以监听 | P0 | `runner.py` |
| CB-05 | 配置项 | Config 新增 `circuit_breaker` 配置块，支持 `max_tokens` / `max_cost_usd` / `loop_detect_turns` / `loop_similarity_threshold` 四个参数 | P0 | `config.py` |

#### 接口设计

**config.py 新增：**

```python
class CircuitBreakerConfig(BaseModel):
    enabled: bool = True
    max_tokens: int = 200_000           # 单次任务 token 上限
    max_cost_usd: float = 5.0           # 单次任务成本上限（USD）
    loop_detect_turns: int = 6          # 连续多少轮判定为死循环
    loop_similarity_threshold: float = 0.9
```

**runner.py 新增 StreamEvent：**

```python
@dataclass
class CircuitBreakerEvent:
    reason: str          # "token_limit" | "cost_limit" | "loop_detected"
    tokens_used: int
    cost_usd: float
    event_type: Literal["circuit_breaker"] = "circuit_breaker"
```

**runner.py 执行循环中插入检查点：**

```python
# 在每次 tool call 结束后调用
def _check_circuit_breaker(self) -> None:
    if not self.config.circuit_breaker.enabled:
        return
    cb = self.config.circuit_breaker
    if self._total_tokens > cb.max_tokens:
        raise CircuitBreakerError("token_limit", self._total_tokens)
    if self._estimated_cost > cb.max_cost_usd:
        raise CircuitBreakerError("cost_limit", self._total_tokens)
    if self._is_loop_detected():
        raise CircuitBreakerError("loop_detected", self._total_tokens)
```

#### 验收标准

- 单测：token 超过 max_tokens 时，`run()` 抛出 `CircuitBreakerError`
- 单测：`run_stream()` 在熔断时产出 `CircuitBreakerEvent` 后停止迭代
- 单测：连续 6 次相似 tool call 触发 loop_detected
- config 序列化/反序列化正常，默认值合理

---

### 3.2 ProjectMemory — 跨任务项目记忆

#### 背景

Cody 目前上下文是静态的，CODY.md 需要手动维护。AI 每次任务结束后积累的经验全部丢失，下次任务从零开始。ProjectMemory 解决"跨任务知识积累"问题，与会话内的 context compaction（已有）是两个不同的机制，不要混淆。

#### 需求列表

| 编号 | 功能点 | 描述 | 优先级 | 改动范围 |
|------|--------|------|--------|---------|
| MEM-01 | 记忆存储 | 在 `~/.cody/memory/<project_hash>/` 目录下按类别（`conventions` / `patterns` / `issues` / `decisions`）存储 JSON 文件，每个文件是 MemoryEntry 数组 | P1 | 新建 `memory.py` |
| MEM-02 | 记忆写入 | 任务结束时（DoneEvent 之后），异步触发 memory extractor，让 LLM 从本次对话中提取值得记忆的内容，写入对应类别文件 | P1 | `runner.py` / `memory.py` |
| MEM-03 | 记忆加载 | AgentRunner 初始化时，读取当前 workdir 对应项目的记忆，追加注入 system prompt（在 CODY.md 之后） | P1 | `runner.py` / `memory.py` |
| MEM-04 | 记忆上限 | 每个类别最多保留 50 条，超出时删除最旧的；confidence < 0.3 的条目自动清理 | P2 | `memory.py` |
| MEM-05 | 手动管理 | CLI 增加 `cody memory list` / `cody memory clear` 命令 | P2 | `cli/` |

#### 记忆类别说明

| 类别 | 存什么 |
|------|--------|
| `conventions` | 代码规范、命名约定、注释风格 |
| `patterns` | 设计模式、常用工具函数、项目特有的实现套路 |
| `issues` | 已知 bug、踩过的坑、需要注意的边界条件 |
| `decisions` | 架构决策、技术选型理由，避免 AI 反复质疑已定论的事情 |

#### 数据结构

```python
# memory.py
@dataclass
class MemoryEntry:
    id: str
    content: str
    source_task_id: str
    source_task_title: str
    created_at: str        # ISO format
    confidence: float = 1.0
    tags: list[str] = field(default_factory=list)

class ProjectMemoryStore:
    def __init__(self, project_id: str): ...
    async def add_entries(self, category: str, entries: list[MemoryEntry]) -> None: ...
    def get_memory_for_prompt(self, max_tokens: int = 2000) -> str: ...
    async def cleanup(self) -> None: ...  # 清理低置信度和超量条目
```

#### project_id 计算规则

```python
import hashlib
project_id = hashlib.md5(str(workdir.resolve()).encode()).hexdigest()[:12]
```

#### 验收标准

- 任务完成后，`~/.cody/memory/<id>/` 下出现对应类别 JSON 文件
- 第二次运行同一项目，system prompt 中包含上次提取的记忆内容
- 超过 50 条后旧条目被清理
- `cody memory list` 输出当前项目记忆条数和摘要

---

### 3.3 HumanFeedback — 标准化人工反馈接口

#### 背景

目前 Cody 的 confirm 逻辑完全下放给各 shell 层处理，导致两个问题：一是各 shell 实现不一致；二是用户的反馈（"不对，重来"）没有标准化方式注入下一次执行，只能靠用户重新输入整个 prompt，体验差且信息损失。

#### 需求列表

| 编号 | 功能点 | 描述 | 优先级 | 改动范围 |
|------|--------|------|--------|---------|
| HF-01 | HumanFeedback 数据结构 | 定义标准化的 `HumanFeedback` dataclass，包含 `action`（approve/reject/revise）、`comment`、`revised_content` 三个字段 | P1 | 新建 `feedback.py` |
| HF-02 | FeedbackRequestEvent | runner.py 在触发 CONFIRM 级别工具时，产出 `FeedbackRequestEvent`（含工具名、参数、建议操作），加入 StreamEvent union type | P1 | `runner.py` |
| HF-03 | 反馈注入机制 | `AgentRunner` 提供 `submit_feedback(feedback: HumanFeedback)` 方法，将反馈结构化注入当前会话的下一轮 prompt | P1 | `runner.py` |
| HF-04 | 置信度自评 | system prompt 增加指令，要求 AI 在不确定时主动输出 `<confidence>0.x</confidence>` 标记，runner.py 解析并在低于阈值时自动产出 `FeedbackRequestEvent` | P2 | `runner.py` / `prompt.py` |
| HF-05 | CLI 支持 | `cody chat` 交互模式在收到 `FeedbackRequestEvent` 时展示确认界面，接收用户输入后调用 `submit_feedback` | P2 | `cli/` |

#### 接口设计

```python
# feedback.py
@dataclass
class HumanFeedback:
    action: Literal["approve", "reject", "revise"]
    comment: str = ""
    revised_content: str = ""   # action=revise 时填入修改后内容

# runner.py 新增 StreamEvent
@dataclass
class FeedbackRequestEvent:
    tool_name: str
    args: dict[str, Any]
    suggested_action: str               # "approve" | "review"
    confidence: Optional[float] = None  # AI 自评置信度
    event_type: Literal["feedback_request"] = "feedback_request"

# AgentRunner 新增方法
class AgentRunner:
    async def submit_feedback(self, feedback: HumanFeedback) -> None:
        """将反馈注入下一轮执行的 message history"""
        ...
```

**反馈注入到 prompt 的格式：**

```
[Human Feedback]
Action: reject
Comment: 不要修改 tests/ 目录下的文件，只改 src/
Please adjust your approach accordingly.
```

#### 验收标准

- `run_stream()` 在触发 CONFIRM 工具时产出 `FeedbackRequestEvent`
- `submit_feedback(reject, comment="...")` 后，下一轮 prompt 包含反馈内容
- SDK 层可以正常监听 `FeedbackRequestEvent` 并异步提交反馈
- CLI chat 模式展示确认提示并正确处理三种 action

---

### 3.4 StructuredOutput — 结构化任务输出

#### 背景

当前 `CodyResult.output` 是纯文本字符串，上层调用方无法基于结构化字段做决策，只能靠解析字符串，非常脆弱。结构化输出也是 ProjectMemory 提取记忆、HumanFeedback 判断置信度的数据基础。

#### 需求列表

| 编号 | 功能点 | 描述 | 优先级 | 改动范围 |
|------|--------|------|--------|---------|
| SO-01 | CodyResult 扩展 | 在 `CodyResult` 新增 `metadata: Optional[TaskMetadata]` 字段，与现有 `output` 并列，不破坏现有接口 | P1 | `runner.py` |
| SO-02 | metadata 提取 | DoneEvent 后，用轻量 LLM 调用（或规则解析）从 output 中提取并填充 metadata | P1 | `runner.py` |
| SO-03 | 置信度解析 | `metadata.confidence` 优先从 AI 输出的 `<confidence>` 标记解析，无标记时默认 `None` | P1 | `runner.py` |
| SO-04 | SDK 暴露 | `AsyncCodyClient.run()` 返回值直接携带 `metadata`，SDK 文档同步更新 | P2 | `sdk/client.py` |

#### 数据结构

```python
# runner.py 扩展
@dataclass
class TaskMetadata:
    summary: str = ""                               # AI 本次做了什么（一句话）
    confidence: Optional[float] = None             # 0-1，AI 自评置信度
    issues: list[str] = field(default_factory=list)      # 遇到的问题
    next_steps: list[str] = field(default_factory=list)  # 建议下一步

@dataclass
class CodyResult:
    output: str                          # 现有字段，不变
    thinking: Optional[str] = None       # 现有字段，不变
    tool_traces: list[ToolTrace] = ...   # 现有字段，不变
    metadata: Optional[TaskMetadata] = None   # 新增，默认 None
    _raw_result: Any = ...               # 现有字段，不变
```

#### 验收标准

- `result.metadata` 在正常任务完成后不为 None
- `result.metadata.summary` 是可读的一句话摘要
- AI 输出包含 `<confidence>0.7</confidence>` 时，`metadata.confidence == 0.7`
- 现有调用 `result.output` 的代码零改动

---

## 4. 优先级与排期建议

### 4.1 优先级汇总

| 编号 | 模块 | P0 | P1 | P2 |
|------|------|----|----|----|
| CB | CircuitBreaker | CB-01, CB-04, CB-05 | CB-02, CB-03 | — |
| SO | StructuredOutput | — | SO-01, SO-02, SO-03 | SO-04 |
| HF | HumanFeedback | — | HF-01, HF-02, HF-03 | HF-04, HF-05 |
| MEM | ProjectMemory | — | MEM-01, MEM-02, MEM-03 | MEM-04, MEM-05 |

### 4.2 建议实现顺序

**第一阶段（独立、收益大、改动小）**

1. `CircuitBreaker` P0 部分（CB-01, CB-04, CB-05）—— 1-2 天
2. `StructuredOutput` P1 部分（SO-01, SO-02, SO-03）—— 3-5 天

> 这两个模块相互独立，可以并行。StructuredOutput 完成后，后续 HumanFeedback 和 ProjectMemory 都有了数据基础。

**第二阶段（依赖第一阶段）**

3. `HumanFeedback` P1 部分（HF-01, HF-02, HF-03）—— 1 周
4. `CircuitBreaker` P1 部分（CB-02, CB-03）—— 2-3 天

**第三阶段（工程量较大）**

5. `ProjectMemory` P1 部分（MEM-01, MEM-02, MEM-03）—— 2 周
6. 各模块 P2 补全 —— 视资源决定

### 4.3 依赖关系

```
CircuitBreaker ────────────────────────────────► 可独立完成
StructuredOutput ──────────────────────────────► 可独立完成
                     │
                     ▼
HumanFeedback ◄── 依赖 StructuredOutput（置信度字段）
ProjectMemory ◄── 依赖 StructuredOutput（summary 用于记忆提取）
```

---

## 5. 不在本次范围内的事项

以下内容超出单 Agent 场景范畴，不在本次需求范围内，后续如果 Cody 向多 Agent 方向演进可以单独立项：

- 多 Agent 编排（StageGraph / DAG 依赖图）
- 固定角色流水线（spec → coding → test → review）
- 跨 Agent 的上下文传递与压缩
- 容器级沙箱隔离（Docker / VM）
- WebSocket 实时状态推送（当前 StreamEvent 已够用）

---

## 6. 附录：关键文件索引

| 文件 | 本次涉及的改动 |
|------|--------------|
| `cody/core/runner.py` | 加入熔断检查点、FeedbackRequestEvent、metadata 提取逻辑、ProjectMemory 加载 |
| `cody/core/config.py` | 新增 `CircuitBreakerConfig` 配置块 |
| `cody/core/memory.py` | 全新文件，ProjectMemoryStore 实现 |
| `cody/core/feedback.py` | 全新文件，HumanFeedback / FeedbackRequestEvent 定义 |
| `cody/core/prompt.py` | 增加置信度自评指令 |
| `cody/sdk/client.py` | 暴露 metadata 字段 |
| `cody/cli/commands/` | memory 子命令，chat 模式的 FeedbackRequest UI |