# SDK 流取消测试

测试 `cancel_event` 参数中止流式执行。

---

## TC-CAN-001: 通过 cancel_event 取消流

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `AsyncCodyClient.stream(cancel_event=)`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/can_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_cancel.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    client = Cody().workdir("/tmp").lsp_languages([]).build()
    cancel = asyncio.Event()
    chunks_received = 0
    got_cancelled = False

    async with client:
        async for chunk in client.stream(
            "Write a very long detailed essay about the history of computing, "
            "at least 2000 words",
            cancel_event=cancel,
        ):
            if chunk.type == "text_delta":
                chunks_received += 1
                # Cancel after receiving 5 text chunks
                if chunks_received >= 5:
                    cancel.set()
            elif chunk.type == "cancelled":
                got_cancelled = True
                break
            elif chunk.type == "done":
                break

    print(f"CHUNKS_RECEIVED: {chunks_received}")
    print(f"GOT_CANCELLED: {got_cancelled}")
    print(f"EARLY_STOP: {chunks_received < 100}")  # Should stop early

asyncio.run(main())
# Note: cancel may produce stderr warnings from pydantic-ai internals; this is expected
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_cancel.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 流在收到少量 chunk 后被取消
- 收到 `cancelled` 类型的 chunk

### 验证方法

```bash
grep "GOT_CANCELLED: True" "$TEST_DIR/output.log" && echo "PASS: cancelled event received" || echo "FAIL: no cancel event"
grep "EARLY_STOP: True" "$TEST_DIR/output.log" && echo "PASS: stopped early" || echo "FAIL: did not stop early"
```
