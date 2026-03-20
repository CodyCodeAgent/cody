# SDK 熔断器测试

测试 Circuit Breaker 功能：token/cost 上限、死循环检测、自动终止失控 Agent。

---

## TC-CB-001: 熔断器 Builder 配置

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `Cody().circuit_breaker()` Builder API

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cb_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_cb_config.py" << 'PYEOF'
import asyncio
from cody import Cody

async def main():
    # 使用 Builder 配置熔断器
    client = Cody().workdir("/tmp").circuit_breaker(
        max_tokens=100000,
        max_cost_usd=2.0,
    ).build()

    # 验证配置已生效
    runner = client.get_runner()
    cb_config = runner._config.circuit_breaker
    print(f"CB_ENABLED: {cb_config.enabled}")
    print(f"MAX_TOKENS: {cb_config.max_tokens}")
    print(f"MAX_COST: {cb_config.max_cost_usd}")

    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
python3 "$TEST_DIR/test_cb_config.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 熔断器配置正确传递到 core
- `max_tokens` 为 100000
- `max_cost_usd` 为 2.0

### 验证方法

```bash
grep "CB_ENABLED: True" "$TEST_DIR/output.log" && echo "PASS: cb enabled" || echo "FAIL: cb not enabled"
grep "MAX_TOKENS: 100000" "$TEST_DIR/output.log" && echo "PASS: max_tokens" || echo "FAIL: wrong max_tokens"
grep "MAX_COST: 2.0" "$TEST_DIR/output.log" && echo "PASS: max_cost" || echo "FAIL: wrong max_cost"
```

---

## TC-CB-002: 熔断器 Token 上限触发

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `CircuitBreakerEvent` 在 token 超限时触发

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cb_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_cb_token_limit.py" << 'PYEOF'
import asyncio
from cody import Cody

async def main():
    # 设置极低的 token 上限
    client = Cody().workdir("/tmp").circuit_breaker(
        max_tokens=100,
        max_cost_usd=100.0,
    ).build()

    chunks = []
    async for chunk in client.stream("写一篇 1000 字的关于 Python 历史的文章"):
        chunks.append(chunk)
        print(f"EVENT: {chunk.type}")

    types = [c.type for c in chunks]
    print(f"HAS_CB_EVENT: {'circuit_breaker' in types}")
    print(f"HAS_DONE: {'done' in types}")

    # CircuitBreakerEvent 应该包含 reason
    cb_events = [c for c in chunks if c.type == "circuit_breaker"]
    if cb_events:
        print(f"CB_REASON_EXISTS: {bool(getattr(cb_events[0], 'reason', ''))}")

    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
python3 "$TEST_DIR/test_cb_token_limit.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 流式输出中出现 `circuit_breaker` 事件
- 任务被自动终止，不会继续生成
- CircuitBreakerEvent 包含 reason 字段

### 验证方法

```bash
grep "HAS_CB_EVENT: True" "$TEST_DIR/output.log" && echo "PASS: circuit breaker triggered" || echo "FAIL: no cb event"
grep "CB_REASON_EXISTS: True" "$TEST_DIR/output.log" && echo "PASS: has reason" || echo "FAIL: no reason"
```

---

## TC-CB-003: 熔断器默认配置正常运行

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: 默认熔断器配置不影响正常短任务

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cb_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_cb_default.py" << 'PYEOF'
import asyncio
from cody import Cody

async def main():
    # 使用默认熔断器配置（max_tokens=200000, max_cost=5.0）
    client = Cody().workdir("/tmp").circuit_breaker().build()

    # 简短任务不应触发熔断
    result = await client.run("回复两个字：收到")

    print(f"HAS_OUTPUT: {bool(result.output)}")
    print(f"OUTPUT: {result.output}")

    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
python3 "$TEST_DIR/test_cb_default.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 简短任务正常完成，不触发熔断
- 输出非空

### 验证方法

```bash
grep "HAS_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: task completed normally" || echo "FAIL: no output"
```
