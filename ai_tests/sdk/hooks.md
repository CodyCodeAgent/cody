# SDK 工具钩子测试

测试 `.before_tool()` 和 `.after_tool()` 中间件功能。

---

## TC-HK-001: before_tool 钩子记录调用

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.before_tool()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/hk_001"
mkdir -p "$TEST_DIR/workdir"
echo "hook test file" > "$TEST_DIR/workdir/test.txt"
cat > "$TEST_DIR/test_before_hook.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import Cody

hook_log = []

async def log_hook(tool_name: str, args: dict) -> dict:
    hook_log.append(tool_name)
    return args  # Proceed unchanged

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    client = Cody().workdir(workdir).before_tool(log_hook).build()
    async with client:
        result = await client.run("Read the file test.txt in the current directory")
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"HOOK_CALLED: {len(hook_log) > 0}")
        print(f"TOOLS_SEEN: {hook_log}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_before_hook.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- before_tool 钩子被调用，记录了工具名
- 任务正常完成

### 验证方法

```bash
grep "HOOK_CALLED: True" "$TEST_DIR/output.log" && echo "PASS: hook called" || echo "FAIL: hook not called"
grep "HAS_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: has output" || echo "FAIL: no output"
```

---

## TC-HK-002: before_tool 钩子拒绝调用

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: before_tool 返回 None 拒绝工具调用

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/hk_002"
mkdir -p "$TEST_DIR/workdir"
cat > "$TEST_DIR/test_reject_hook.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import Cody

rejected = []

async def block_exec(tool_name: str, args: dict) -> dict | None:
    if tool_name == "exec_command":
        rejected.append(args.get("command", ""))
        return None  # Reject
    return args

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    client = Cody().workdir(workdir).before_tool(block_exec).build()
    async with client:
        result = await client.run("Run the command: echo hello")
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"REJECTED_COUNT: {len(rejected)}")
        print(f"REJECTED: {rejected}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_reject_hook.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- exec_command 被钩子拦截
- Agent 可能收到 retry 提示并选择其他方式

### 验证方法

```bash
grep "REJECTED_COUNT:" "$TEST_DIR/output.log" | grep -v "REJECTED_COUNT: 0" && echo "PASS: command rejected" || echo "FAIL: not rejected"
```

---

## TC-HK-003: after_tool 钩子转换输出

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.after_tool()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/hk_003"
mkdir -p "$TEST_DIR/workdir"
echo "SECRET_KEY=abc123xyz" > "$TEST_DIR/workdir/config.txt"
cat > "$TEST_DIR/test_after_hook.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import Cody

redacted = False

async def redact_hook(tool_name: str, args: dict, result: str) -> str:
    global redacted
    if "abc123xyz" in result:
        redacted = True
        result = result.replace("abc123xyz", "***REDACTED***")
    return result

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    client = Cody().workdir(workdir).after_tool(redact_hook).build()
    async with client:
        result = await client.run("Read config.txt and tell me what's in it")
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"REDACTED: {redacted}")
        # The secret should NOT appear in the final output
        secret_leaked = "abc123xyz" in result.output
        print(f"SECRET_LEAKED: {secret_leaked}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_after_hook.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- after_tool 钩子对工具输出进行脱敏
- 模型看到的是脱敏后的结果

### 验证方法

```bash
grep "REDACTED: True" "$TEST_DIR/output.log" && echo "PASS: redaction hook worked" || echo "FAIL: not redacted"
```
