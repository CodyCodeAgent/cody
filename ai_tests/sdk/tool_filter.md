# SDK 工具过滤测试

测试 `include_tools` / `exclude_tools` 参数控制可用工具范围。

---

## TC-TF-001: exclude_tools 禁用特定工具

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `run(exclude_tools=)` / `stream(exclude_tools=)`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/tf_001"
mkdir -p "$TEST_DIR/workdir"
echo "filter test" > "$TEST_DIR/workdir/test.txt"
cat > "$TEST_DIR/test_exclude.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import Cody

tools_used = []

async def track_tools(tool_name: str, args: dict) -> dict:
    tools_used.append(tool_name)
    return args

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    client = Cody().workdir(workdir).before_tool(track_tools).build()
    async with client:
        result = await client.run(
            "Read test.txt and run 'echo hello'",
            exclude_tools={"exec_command"},
        )
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"TOOLS_USED: {tools_used}")
        exec_used = "exec_command" in tools_used
        print(f"EXEC_BLOCKED: {not exec_used}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_exclude.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- `exec_command` 不在可用工具列表中，Agent 无法调用
- 其他工具（如 `read_file`）正常可用

### 验证方法

```bash
grep "EXEC_BLOCKED: True" "$TEST_DIR/output.log" && echo "PASS: exec_command blocked" || echo "FAIL: exec_command used"
```

---

## TC-TF-002: include_tools 只启用指定工具

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `run(include_tools=)`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/tf_002"
mkdir -p "$TEST_DIR/workdir"
echo "include test" > "$TEST_DIR/workdir/data.txt"
cat > "$TEST_DIR/test_include.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import Cody

tools_used = []

async def track_tools(tool_name: str, args: dict) -> dict:
    tools_used.append(tool_name)
    return args

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    client = Cody().workdir(workdir).before_tool(track_tools).build()
    async with client:
        result = await client.run(
            "Read data.txt in the current directory",
            include_tools={"read_file", "list_directory"},
        )
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"TOOLS_USED: {tools_used}")
        all_allowed = all(t in {"read_file", "list_directory"} for t in tools_used)
        print(f"ALL_TOOLS_ALLOWED: {all_allowed}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_include.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 只使用 include 列表中的工具

### 验证方法

```bash
grep "ALL_TOOLS_ALLOWED: True" "$TEST_DIR/output.log" && echo "PASS: only allowed tools used" || echo "FAIL: unauthorized tools used"
```
