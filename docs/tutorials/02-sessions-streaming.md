# 02 · 会话与流式输出

<div class="tutorial-outcome"><strong>完成后：</strong>你会在同一个 session 中连续推进任务，并正确处理 session、文本、工具、重试与终态事件。</div>

## 1. 显式创建会话

```python
import asyncio

from cody import AsyncCodyClient


async def main() -> None:
    async with AsyncCodyClient(workdir="/tmp/cody-tutorial") as client:
        session = await client.create_session(title="教程项目")

        first = await client.run(
            "读取 hello.py，并为它补一个 main() 函数",
            session_id=session.id,
        )
        second = await client.run(
            "沿用上一轮的实现，为 main() 添加 pytest 测试",
            session_id=session.id,
        )

        print(first.session_id, second.session_id)


asyncio.run(main())
```

两次 `run()` 必须使用同一个 `session_id` 才会共享消息历史。没有传入时，Cody 会为本次调用自动创建 session。

## 2. 消费流式事件

```python
import asyncio

from cody import AsyncCodyClient


async def main() -> None:
    async with AsyncCodyClient(workdir="/tmp/cody-tutorial") as client:
        async for chunk in client.stream("运行测试并修复失败项"):
            if chunk.type == "session_start":
                print(f"session={chunk.session_id} run={chunk.run_id}")
            elif chunk.type == "text_delta":
                print(chunk.content, end="", flush=True)
            elif chunk.type == "tool_call":
                print(f"\n→ {chunk.tool_name} {chunk.args}")
            elif chunk.type == "tool_result":
                print(f"\n✓ {chunk.tool_name}")
            elif chunk.type == "retry":
                print(f"\n重试 {chunk.retry_attempt}/{chunk.retry_max_attempts}")
            elif chunk.type in {"done", "cancelled", "circuit_breaker"}:
                print(f"\n终态：{chunk.type}")


asyncio.run(main())
```

`run_stream()` 是 `stream()` 的兼容别名。同步 `CodyClient.stream()` 会一次返回完整列表，不是真正的异步增量流。

## 3. 正确处理重试

模型端点在已经返回部分文本后也可能失败。收到 `retry` 时，界面应清空本轮尚未提交的临时文本，等待下一次尝试；不要把两次尝试拼成一段结果。

## 4. 主动取消

```python
cancel = asyncio.Event()

async for chunk in client.stream("执行长任务", cancel_event=cancel):
    if should_stop():
        cancel.set()
```

取消会传播到模型和工具执行边界。需要跨进程取消时，使用 Runtime 控制命令，而不是只设置本进程的 `asyncio.Event`。

## 验证清单

- 首个 chunk 是 `session_start`。
- 同一会话的多个调用返回相同 `session_id`。
- UI 能区分临时流式文本和最终 `done`。
- `retry`、`cancelled`、`circuit_breaker` 不会被误当成普通文本。
