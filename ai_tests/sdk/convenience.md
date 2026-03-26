# SDK 便捷方法测试

测试 `AsyncCodyClient` 的便捷方法（直接操作，不经过 Agent）。

---

## TC-CV-001: read_file 便捷方法

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `AsyncCodyClient.read_file()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cv_001"
mkdir -p "$TEST_DIR/workdir"
echo "convenience read test 12345" > "$TEST_DIR/workdir/sample.txt"
cat > "$TEST_DIR/test_convenience.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import AsyncCodyClient

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    async with AsyncCodyClient(workdir=workdir) as client:
        # read_file
        content = await client.read_file(os.path.join(workdir, "sample.txt"))
        print(f"READ_OK: {'convenience read test 12345' in content}")

        # write_file
        target = os.path.join(workdir, "written.txt")
        await client.write_file(target, "written by convenience method")
        exists = os.path.isfile(target)
        print(f"WRITE_OK: {exists}")

        # edit_file
        await client.edit_file(target, "written by convenience method", "edited content")
        edited = open(target).read()
        print(f"EDIT_OK: {'edited content' in edited}")

        # list_directory
        listing = await client.list_directory(workdir)
        has_files = "sample.txt" in listing and "written.txt" in listing
        print(f"LIST_OK: {has_files}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_convenience.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- read_file / write_file / edit_file / list_directory 全部正常

### 验证方法

```bash
grep "READ_OK: True" "$TEST_DIR/output.log" && echo "PASS: read" || echo "FAIL: read"
grep "WRITE_OK: True" "$TEST_DIR/output.log" && echo "PASS: write" || echo "FAIL: write"
grep "EDIT_OK: True" "$TEST_DIR/output.log" && echo "PASS: edit" || echo "FAIL: edit"
grep "LIST_OK: True" "$TEST_DIR/output.log" && echo "PASS: list" || echo "FAIL: list"
```

---

## TC-CV-002: grep 和 glob 便捷方法

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `AsyncCodyClient.grep()`, `AsyncCodyClient.glob()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cv_002"
mkdir -p "$TEST_DIR/workdir/sub"
echo "def main(): pass" > "$TEST_DIR/workdir/app.py"
echo "def helper(): pass" > "$TEST_DIR/workdir/sub/utils.py"
cat > "$TEST_DIR/test_search.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import AsyncCodyClient

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    async with AsyncCodyClient(workdir=workdir) as client:
        # glob
        files = await client.glob("**/*.py")
        has_py = "app.py" in files
        print(f"GLOB_OK: {has_py}")
        print(f"GLOB_RESULT: {files[:200]}")

        # grep
        matches = await client.grep("def main", include="*.py")
        has_match = "main" in matches
        print(f"GREP_OK: {has_match}")
        print(f"GREP_RESULT: {matches[:200]}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_search.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- glob 找到 `.py` 文件
- grep 找到 `def main` 匹配

### 验证方法

```bash
grep "GLOB_OK: True" "$TEST_DIR/output.log" && echo "PASS: glob works" || echo "FAIL: glob failed"
grep "GREP_OK: True" "$TEST_DIR/output.log" && echo "PASS: grep works" || echo "FAIL: grep failed"
```

---

## TC-CV-003: exec_command 便捷方法

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `AsyncCodyClient.exec_command()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cv_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_exec.py" << 'PYEOF'
import asyncio
from cody.sdk import AsyncCodyClient

async def main():
    async with AsyncCodyClient(workdir="/tmp") as client:
        output = await client.exec_command("echo EXEC_TEST_12345")
        has_marker = "EXEC_TEST_12345" in output
        print(f"EXEC_OK: {has_marker}")
        print(f"OUTPUT: {output[:200]}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_exec.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 命令执行成功，输出包含标记字符串

### 验证方法

```bash
grep "EXEC_OK: True" "$TEST_DIR/output.log" && echo "PASS: exec works" || echo "FAIL: exec failed"
```
