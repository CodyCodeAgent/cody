# SDK 人工交互测试

测试 Human-in-the-Loop 功能：AI 主动提问 + `submit_interaction()` 回复。

---

## TC-IA-001: 交互配置 Builder

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `Cody().interaction()` Builder API

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ia_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_ia_config.py" << 'PYEOF'
import asyncio
from cody import Cody

async def main():
    client = Cody().workdir("/tmp").interaction(
        enabled=True,
        timeout=60.0,
    ).build()

    # 验证配置已传递到 core
    runner = client.get_runner()
    ia_config = runner.config.interaction
    print(f"IA_ENABLED: {ia_config.enabled}")
    print(f"IA_TIMEOUT: {ia_config.timeout}")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_ia_config.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 交互配置正确传递
- `enabled` 为 True
- `timeout` 为 60.0

### 验证方法

```bash
grep "IA_ENABLED: True" "$TEST_DIR/output.log" && echo "PASS: interaction enabled" || echo "FAIL: not enabled"
grep "IA_TIMEOUT: 60.0" "$TEST_DIR/output.log" && echo "PASS: timeout set" || echo "FAIL: wrong timeout"
```

---

## TC-IA-002: 交互事件流中出现 interaction_request

**优先级**: P1
**前置条件**: cody 已安装，需要能触发 `question` 工具的提示
**涉及功能**: `InteractionRequestEvent` 在流式输出中出现

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ia_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_ia_event.py" << 'PYEOF'
import asyncio
from cody import Cody

async def main():
    client = Cody().workdir("/tmp").interaction(
        enabled=True,
        timeout=10.0,
    ).build()

    # 用一个需要确认的提示来触发交互
    # 注意：这依赖 AI 判断是否需要向用户提问
    chunks = []
    try:
        async for chunk in client.stream(
            "你好，请用 question 工具向我提一个问题，问我想用什么编程语言"
        ):
            chunks.append(chunk)
            print(f"EVENT: {chunk.type}")

            # 如果收到交互请求，自动回复
            if chunk.type == "interaction_request":
                request_id = getattr(chunk, "request_id", None)
                if request_id:
                    await client.submit_interaction(
                        request_id=request_id,
                        action="answer",
                        content="Python",
                    )
                    print("SUBMITTED_RESPONSE: True")
    except Exception as e:
        print(f"ERROR: {e}")

    types = [c.type for c in chunks]
    print(f"CHUNK_TYPES: {sorted(set(types))}")
    print(f"HAS_EVENTS: {len(chunks) > 0}")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
timeout 120 python3 "$TEST_DIR/test_ia_event.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 流式输出中包含事件
- 如果 AI 选择提问，会出现 `interaction_request` 事件
- `submit_interaction` 成功回复

### 验证方法

```bash
grep "HAS_EVENTS: True" "$TEST_DIR/output.log" && echo "PASS: received events" || echo "FAIL: no events"
# interaction_request 是可选验证（AI 不一定总是提问）
grep "SUBMITTED_RESPONSE: True" "$TEST_DIR/output.log" && echo "PASS: interaction submitted" || echo "INFO: no interaction triggered (AI may not have asked)"
```

---

## TC-IA-003: 交互禁用时自动跳过

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `interaction(enabled=False)` 时交互自动跳过

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ia_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_ia_disabled.py" << 'PYEOF'
import asyncio
from cody import Cody

async def main():
    # 禁用交互 — 这是默认行为
    client = Cody().workdir("/tmp").build()

    result = await client.run("回复两个字：收到")
    print(f"HAS_OUTPUT: {bool(result.output)}")
    print(f"COMPLETED: True")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_ia_disabled.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 禁用交互时任务正常完成
- 不会阻塞等待用户输入

### 验证方法

```bash
grep "COMPLETED: True" "$TEST_DIR/output.log" && echo "PASS: completed without interaction" || echo "FAIL: blocked or failed"
```
