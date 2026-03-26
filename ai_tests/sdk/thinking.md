# SDK 思考模式测试

测试 `.thinking()` Builder 方法和思考内容输出。

> **注意**：思考模式需要模型支持（如 Claude Sonnet 4）。不支持的模型测试会 SKIP。

---

## TC-TH-001: 思考模式配置

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.thinking()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/th_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_thinking_config.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    client = (
        Cody()
        .workdir("/tmp")
        .thinking(True, budget=5000)
        .build()
    )
    print(f"BUILD_OK: True")
    print(f"THINKING_ENABLED: {client._config.model.enable_thinking}")
    print(f"THINKING_BUDGET: {client._config.model.thinking_budget}")
    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_thinking_config.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- thinking 配置正确传递

### 验证方法

```bash
grep "BUILD_OK: True" "$TEST_DIR/output.log" && echo "PASS: build ok" || echo "FAIL: build failed"
grep "THINKING_ENABLED: True" "$TEST_DIR/output.log" && echo "PASS: thinking enabled" || echo "FAIL: thinking not enabled"
grep "THINKING_BUDGET: 5000" "$TEST_DIR/output.log" && echo "PASS: budget set" || echo "FAIL: wrong budget"
```

---

## TC-TH-002: 思考模式流式输出

**优先级**: P2
**前置条件**: cody 已安装, 模型支持思考模式
**涉及功能**: `stream()` 中的 `thinking` 类型 chunk

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/th_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_thinking_stream.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    client = Cody().workdir("/tmp").thinking(True, budget=5000).build()
    chunk_types = set()

    async with client:
        async for chunk in client.stream("What is 17 * 23? Think step by step."):
            chunk_types.add(chunk.type)

    print(f"CHUNK_TYPES: {sorted(chunk_types)}")
    has_thinking = "thinking" in chunk_types
    has_text = "text_delta" in chunk_types
    print(f"HAS_THINKING: {has_thinking}")
    print(f"HAS_TEXT: {has_text}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_thinking_stream.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 流中出现 `thinking` 类型 chunk
- 也有正常的 `text_delta` 输出

### 验证方法

```bash
grep "HAS_THINKING: True" "$TEST_DIR/output.log" && echo "PASS: thinking chunks" || echo "SKIP: model may not support thinking"
grep "HAS_TEXT: True" "$TEST_DIR/output.log" && echo "PASS: text output" || echo "FAIL: no text"
```
