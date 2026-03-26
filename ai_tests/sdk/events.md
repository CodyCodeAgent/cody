# SDK 事件系统与指标测试

测试事件钩子 `.on()` 和指标收集 `.enable_metrics()`。

---

## TC-EV-001: 事件系统监听工具调用

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.on()`, `EventType.TOOL_CALL`, `EventType.TOOL_RESULT`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ev_001"
mkdir -p "$TEST_DIR/workdir"
echo "event test file" > "$TEST_DIR/workdir/hello.txt"
cat > "$TEST_DIR/test_events.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import Cody

tool_calls = []
tool_results = []

def on_tool_call(event):
    tool_calls.append(event.tool_name)

def on_tool_result(event):
    tool_results.append(event.tool_name)

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    client = (
        Cody()
        .workdir(workdir)
        .on("tool_call", on_tool_call)
        .on("tool_result", on_tool_result)
        .build()
    )
    async with client:
        result = await client.run("Read hello.txt")
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"TOOL_CALLS: {tool_calls}")
        print(f"TOOL_RESULTS: {tool_results}")
        print(f"HAS_EVENTS: {len(tool_calls) > 0 and len(tool_results) > 0}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_events.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- tool_call 和 tool_result 事件被触发
- 事件中包含工具名称

### 验证方法

```bash
grep "HAS_EVENTS: True" "$TEST_DIR/output.log" && echo "PASS: events fired" || echo "FAIL: no events"
```

---

## TC-EV-002: 指标收集

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.enable_metrics()`, `client.get_metrics()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ev_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_metrics.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    client = Cody().workdir("/tmp").enable_metrics().build()
    async with client:
        await client.run("回复 OK")
        metrics = client.get_metrics()
        print(f"HAS_METRICS: {metrics is not None}")
        if metrics:
            print(f"TOTAL_RUNS: {metrics.get('total_runs', 0)}")
            print(f"TOTAL_TOKENS: {metrics.get('total_tokens', 0)}")
            print(f"RUNS_GT_ZERO: {metrics.get('total_runs', 0) > 0}")
            print(f"TOKENS_GT_ZERO: {metrics.get('total_tokens', 0) > 0}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_metrics.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 指标包含 total_runs 和 total_tokens
- 值大于 0

### 验证方法

```bash
grep "RUNS_GT_ZERO: True" "$TEST_DIR/output.log" && echo "PASS: run counted" || echo "FAIL: no runs"
grep "TOKENS_GT_ZERO: True" "$TEST_DIR/output.log" && echo "PASS: tokens counted" || echo "FAIL: no tokens"
```
