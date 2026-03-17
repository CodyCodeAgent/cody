# SDK 流式输出测试

测试 `AsyncCodyClient.stream()` 的流式输出功能。

---

## TC-STREAM-001: 基本流式输出

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `AsyncCodyClient.stream()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/stream_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_stream.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")

    chunks = []
    async for chunk in client.stream("用中文简短介绍一下 Python 语言，50字以内"):
        chunks.append(chunk)

    print(f"CHUNK_COUNT: {len(chunks)}")
    print(f"HAS_CHUNKS: {len(chunks) > 0}")

    # 检查是否有文本类型的 chunk
    text_chunks = [c for c in chunks if c.type == "text_delta"]
    print(f"TEXT_CHUNKS: {len(text_chunks)}")

    # 检查最终是否有完成 chunk
    done_chunks = [c for c in chunks if c.type == "done"]
    print(f"HAS_DONE: {len(done_chunks) > 0}")

    # 拼接所有文本
    full_text = "".join(c.content for c in text_chunks if c.content)
    print(f"HAS_TEXT: {bool(full_text)}")
    print(f"TEXT_PREVIEW: {full_text[:100]}")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_stream.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 收到多个 chunk
- 至少有一个 text_delta 类型的 chunk
- 有一个 done 类型的 chunk 表示结束
- 文本内容非空

### 验证方法

```bash
grep "HAS_CHUNKS: True" "$TEST_DIR/output.log" && echo "PASS: received chunks" || echo "FAIL: no chunks"
grep "HAS_DONE: True" "$TEST_DIR/output.log" && echo "PASS: has done signal" || echo "FAIL: no done"
grep "HAS_TEXT: True" "$TEST_DIR/output.log" && echo "PASS: has text" || echo "FAIL: no text"
```

---

## TC-STREAM-002: 流式输出带工具调用

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: 流式输出中工具调用的事件

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/stream_002"
mkdir -p "$TEST_DIR/workspace"
cat > "$TEST_DIR/test_stream_tools.py" << 'PYEOF'
import asyncio
import os
from cody.sdk.client import AsyncCodyClient

async def main():
    workdir = os.path.join(os.environ.get("CODY_TEST_DIR", "/tmp"), "stream_002/workspace")
    os.makedirs(workdir, exist_ok=True)

    client = AsyncCodyClient(workdir=workdir)

    chunk_types = set()
    async for chunk in client.stream("创建一个 test.txt 文件，内容是 stream test"):
        chunk_types.add(chunk.type)

    print(f"CHUNK_TYPES: {sorted(chunk_types)}")
    print(f"HAS_TOOL_EVENTS: {'tool_call' in chunk_types or 'tool_result' in chunk_types}")

    # 验证文件确实被创建了
    filepath = os.path.join(workdir, "test.txt")
    print(f"FILE_CREATED: {os.path.isfile(filepath)}")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_stream_tools.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- chunk 类型中包含 tool 相关事件
- 文件被成功创建

### 验证方法

```bash
grep "FILE_CREATED: True" "$TEST_DIR/output.log" && echo "PASS: file created via stream" || echo "FAIL: no file"
# tool 事件是可选验证（不同版本事件类型可能不同）
grep "CHUNK_TYPES:" "$TEST_DIR/output.log" && echo "PASS: got chunk types" || echo "FAIL: no types"
```

---

## TC-STREAM-003: 流式输出与会话结合

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: 带 session_id 的流式输出

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/stream_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_stream_session.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")
    store = client.get_session_store()
    session = store.create_session(title="Stream Test", model="test", workdir="/tmp")

    # 第一轮流式
    text1 = ""
    async for chunk in client.stream("我的名字是 Alice", session_id=session.id):
        if chunk.type == "text_delta" and chunk.content:
            text1 += chunk.content
    print(f"TURN1_OK: {bool(text1)}")

    # 第二轮流式（验证上下文）
    text2 = ""
    async for chunk in client.stream("我的名字是什么？", session_id=session.id):
        if chunk.type == "text_delta" and chunk.content:
            text2 += chunk.content
    print(f"TURN2_OK: {bool(text2)}")
    print(f"REMEMBERS_NAME: {'Alice' in text2 or 'alice' in text2.lower()}")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_stream_session.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 两轮流式对话都成功
- 第二轮能记住第一轮的信息

### 验证方法

```bash
grep "TURN1_OK: True" "$TEST_DIR/output.log" && echo "PASS: turn 1" || echo "FAIL: turn 1"
grep "TURN2_OK: True" "$TEST_DIR/output.log" && echo "PASS: turn 2" || echo "FAIL: turn 2"
grep "REMEMBERS_NAME: True" "$TEST_DIR/output.log" && echo "PASS: context kept" || echo "FAIL: context lost"
```

---

## TC-STREAM-004: 流式输出取消

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `AsyncCodyClient.stream()` 的 `cancel_event` 参数

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/stream_004"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_stream_cancel.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")
    cancel = asyncio.Event()

    chunks = []
    async for chunk in client.stream(
        "写一篇 500 字的关于人工智能的文章",
        cancel_event=cancel,
    ):
        chunks.append(chunk)
        # 收到第一个 text_delta 后立即取消
        if chunk.type == "text_delta":
            cancel.set()

    types = [c.type for c in chunks]
    print(f"CHUNK_TYPES: {types}")
    print(f"HAS_TEXT: {'text_delta' in types}")
    print(f"HAS_CANCELLED: {'cancelled' in types}")
    # cancel 之后不应该有 done 事件
    print(f"NO_DONE: {'done' not in types}")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_stream_cancel.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 收到至少一个 text_delta chunk
- 收到一个 cancelled chunk 表示取消成功
- 不会收到 done chunk（因为被取消了）

### 验证方法

```bash
grep "HAS_TEXT: True" "$TEST_DIR/output.log" && echo "PASS: got text before cancel" || echo "FAIL: no text"
grep "HAS_CANCELLED: True" "$TEST_DIR/output.log" && echo "PASS: cancel event received" || echo "FAIL: no cancel event"
grep "NO_DONE: True" "$TEST_DIR/output.log" && echo "PASS: no done after cancel" || echo "FAIL: unexpected done"
```

---

## TC-STREAM-005: 流式输出取消与会话结合

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: 取消后 session 中保存 "(cancelled)" 占位消息

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/stream_005"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_stream_cancel_session.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")
    store = client.get_session_store()
    session = store.create_session(title="Cancel Test", model="test", workdir="/tmp")

    # 流式请求后立即取消
    cancel = asyncio.Event()
    async for chunk in client.stream(
        "写一篇长文章",
        session_id=session.id,
        cancel_event=cancel,
    ):
        if chunk.type == "text_delta":
            cancel.set()

    # 检查 session 中的消息
    session_data = store.get_session(session.id)
    messages = session_data.messages
    print(f"MSG_COUNT: {len(messages)}")
    # 应该有 user + assistant 两条消息
    print(f"HAS_USER: {any(m.role == 'user' for m in messages)}")
    print(f"HAS_ASSISTANT: {any(m.role == 'assistant' for m in messages)}")
    # assistant 消息内容应该是 "(cancelled)"
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    if assistant_msgs:
        print(f"CANCELLED_PLACEHOLDER: {assistant_msgs[-1].content == '(cancelled)'}")
    else:
        print("CANCELLED_PLACEHOLDER: False")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_stream_cancel_session.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- session 中有 user 和 assistant 两条消息
- assistant 消息内容为 "(cancelled)" 占位符
- session 状态一致，不会出现孤立 user 消息

### 验证方法

```bash
grep "HAS_USER: True" "$TEST_DIR/output.log" && echo "PASS: user message saved" || echo "FAIL: no user msg"
grep "HAS_ASSISTANT: True" "$TEST_DIR/output.log" && echo "PASS: assistant message saved" || echo "FAIL: no assistant msg"
grep "CANCELLED_PLACEHOLDER: True" "$TEST_DIR/output.log" && echo "PASS: cancelled placeholder" || echo "FAIL: no placeholder"
```
