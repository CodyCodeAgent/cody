# 计划：支持用户随时输入（不等 AI 提问）

## 背景

当前 human-in-the-loop 是严格的 **AI 问 → 人答** 模式。用户只有在 AI 发出 `InteractionRequest` 时才能输入。
目标：**AI 在执行过程中，用户随时可以发一条消息，AI 下一轮会看到。**

## 核心思路

把 runner 的流式执行从 `agent.run_stream_events()`（黑盒）换成 `agent.iter()` + `node.stream()`（逐 node 控制）。
在每个 node 执行完后、下一个 node 开始前，检查用户有没有主动输入。如果有，通过 `CallToolsNode.user_prompt` 注入。

事件流不受影响 — `node.stream()` 产出的事件跟 `run_stream_events()` 完全一样。

## 改动范围

### 第 1 步：新增 `UserInputQueue`（新文件 `core/user_input.py`）

一个简单的 asyncio.Queue wrapper，用于接收用户主动输入：

```python
class UserInputQueue:
    def __init__(self):
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def put(self, message: str) -> None:
        await self._queue.put(message)

    def try_get(self) -> str | None:
        """非阻塞取。没有就返回 None。"""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def drain_all(self) -> list[str]:
        """取出队列中的所有消息。"""
        messages = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages
```

### 第 2 步：改造 `AgentRunner.run_stream()`（`core/runner.py`）

**现在**：`_run_agent()` 后台 task 里调 `agent.run_stream_events()`，把事件推到 `out_q`。

**改成**：直接在 `run_stream()` 里用 `agent.iter()`，不需要后台 task + queue 了。

伪代码：

```python
async def run_stream(self, prompt, ..., user_input_queue=None):
    # ... compact history, yield CompactEvent 等不变 ...

    deps = self._create_deps(interaction_handler=interaction_handler)

    async with self.agent.iter(
        pydantic_prompt, deps=deps, message_history=message_history,
        model_settings=self._build_model_settings(),
    ) as agent_run:
        async for node in agent_run:
            # ── 取消检查 ──
            if cancel_event and cancel_event.is_set():
                yield CancelledEvent()
                return

            # ── ModelRequestNode：流式拿 thinking/text 事件 ──
            if self.agent.is_model_request_node(node):
                async with node.stream(agent_run.ctx) as stream:
                    async for event in stream:
                        # 转换 PartStartEvent/PartDeltaEvent → ThinkingEvent/TextDeltaEvent
                        yield _convert_event(event)

            # ── CallToolsNode：流式拿 tool 事件 ──
            elif self.agent.is_call_tools_node(node):
                # ★ 关键：注入用户输入
                if user_input_queue:
                    messages = user_input_queue.drain_all()
                    if messages:
                        combined = "\n".join(messages)
                        node.user_prompt = combined
                        yield UserInputReceivedEvent(content=combined)

                async with node.stream(agent_run.ctx) as stream:
                    async for event in stream:
                        # 转换 FunctionToolCallEvent/FunctionToolResultEvent
                        yield _convert_event(event)
                        # 同时做 circuit breaker 检查

            elif isinstance(node, End):
                # 最终结果
                result = CodyResult.from_raw(agent_run.result)
                self._update_circuit_breaker(...)
                self._check_circuit_breaker()
                yield DoneEvent(result=result)
```

**为什么注入点在 CallToolsNode**：
- `CallToolsNode` 原生支持 `user_prompt` 字段
- tool 执行完后，`user_prompt` 会作为 `UserPromptPart` 附在 tool results 后面，一起发给 LLM
- LLM 下一轮会同时看到 tool 结果 + 用户的新消息
- 如果 LLM 直接出了 final result（没调 tool），`user_prompt` 被忽略 — 这合理，因为已经结束了

### 第 3 步：新增 `UserInputReceivedEvent`（`core/runner.py`）

```python
@dataclass
class UserInputReceivedEvent:
    """用户主动输入的消息已被接收，将在下一轮 LLM 调用中可见。"""
    content: str
    event_type: Literal["user_input_received"] = "user_input_received"
```

加入 `StreamEvent` union。

### 第 4 步：`AgentRunner` 暴露 `inject_user_input()` 方法

```python
def __init__(self, ...):
    ...
    self._user_input_queue = UserInputQueue()

async def inject_user_input(self, message: str) -> None:
    """用户主动发送消息，不需要 AI 先提问。下一个 node 间隙会被注入。"""
    await self._user_input_queue.put(message)
```

`run_stream()` 把 `self._user_input_queue` 传给内部逻辑。

### 第 5 步：SDK 暴露 API（`sdk/client.py`）

```python
async def inject_user_input(self, message: str) -> None:
    """Send a message to the running agent without waiting for it to ask."""
    runner = self.get_runner()
    await runner.inject_user_input(message)
```

### 第 6 步：Web 后端加路由（`web/backend/routes/`）

```python
@router.post("/sessions/{session_id}/inject")
async def inject_user_input(session_id: str, body: InjectInput):
    runner = get_runner_for_session(session_id)
    await runner.inject_user_input(body.message)
    return {"status": "queued"}
```

WebSocket 协议也加一个 `{"type": "user_input", "content": "..."}` 消息类型。

### 第 7 步：去掉 `_run_agent()` 后台 task + queue 模式

因为 `iter()` 是同步迭代的（在 `run_stream` generator 里），不再需要：
- `out_q: asyncio.Queue`
- `_sentinel` 对象
- `_run_agent()` 后台 task
- consumer loop

整体架构从 **"后台 task 推 queue → consumer 拉 queue yield"** 变成 **"generator 直接 yield"**，更简洁。

### 第 8 步：保留现有 interaction 机制

`InteractionRequest/Response`（AI 主动问人）完全不动。它跑在 tool 内部，`iter()` 不影响。
新增的是 **人主动输入** 这条路，两者并行。

## 不需要改的

- `interaction.py` — InteractionRequest/Response 不动
- `tools/user.py` — question 工具不动
- `run_stream_with_session()` — 它包装 `run_stream()`，自动受益
- CLI/TUI 渲染逻辑 — 只是多了一个 event 类型
- 所有现有 StreamEvent 类型 — 不变

## 测试计划

1. 新增 `tests/test_user_input.py` — 测 `UserInputQueue` 基本行为
2. 新增 runner 集成测试 — mock agent，验证用户输入被注入到 `CallToolsNode.user_prompt`
3. 现有 `tests/test_runner.py` 流式测试 — 确保没 regression
4. Web endpoint 测试 — inject API

## 风险

1. **`iter()` API 稳定性** — pydantic-ai 1.70.0 的 `iter()` 是 documented API，应该稳定
2. **事件顺序** — 需要确保 `node.stream()` 产出的事件跟之前 `run_stream_events()` 一致，需要回归测试
3. **用户输入时机** — 如果 LLM 没调 tool 就直接结束了（没有 CallToolsNode 或 node 间隙），用户的输入会丢失。需要在 `DoneEvent` 之前检查队列，如果有未处理的输入，提示用户
