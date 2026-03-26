# SDK 同步客户端测试

测试 `CodyClient`（同步封装）的核心功能。

---

## TC-SYNC-001: 同步 run 执行

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `CodyClient.run()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sync_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_sync_run.py" << 'PYEOF'
from cody import CodyClient

with CodyClient(workdir="/tmp") as client:
    result = client.run("回复两个字：收到")
    print(f"HAS_OUTPUT: {bool(result.output)}")
    print(f"OUTPUT: {result.output}")
    has_usage = result.usage is not None
    print(f"HAS_USAGE: {has_usage}")
    if has_usage:
        print(f"TOKENS: {result.usage.total_tokens}")
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_sync_run.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 同步 `run()` 正常返回结果
- 无需 `asyncio.run()`

### 验证方法

```bash
grep "HAS_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: sync run works" || echo "FAIL: sync run failed"
grep "HAS_USAGE: True" "$TEST_DIR/output.log" && echo "PASS: has usage" || echo "FAIL: no usage"
```

---

## TC-SYNC-002: 同步 stream 执行

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `CodyClient.stream()`（返回 list）

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sync_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_sync_stream.py" << 'PYEOF'
from cody import CodyClient

with CodyClient(workdir="/tmp") as client:
    chunks = client.stream("回复 OK")
    print(f"IS_LIST: {isinstance(chunks, list)}")
    print(f"CHUNK_COUNT: {len(chunks)}")
    types = [c.type for c in chunks]
    print(f"TYPES: {types}")
    has_text = any(c.type == "text_delta" for c in chunks)
    has_done = any(c.type == "done" for c in chunks)
    print(f"HAS_TEXT: {has_text}")
    print(f"HAS_DONE: {has_done}")
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_sync_stream.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- `stream()` 返回 list（非迭代器）
- 包含 text_delta 和 done 类型的 chunk

### 验证方法

```bash
grep "IS_LIST: True" "$TEST_DIR/output.log" && echo "PASS: is list" || echo "FAIL: not list"
grep "HAS_TEXT: True" "$TEST_DIR/output.log" && echo "PASS: has text" || echo "FAIL: no text"
grep "HAS_DONE: True" "$TEST_DIR/output.log" && echo "PASS: has done" || echo "FAIL: no done"
```

---

## TC-SYNC-003: 同步工具调用

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `CodyClient.tool()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sync_003"
mkdir -p "$TEST_DIR"
echo "sync tool test content" > "$TEST_DIR/sample.txt"
cat > "$TEST_DIR/test_sync_tool.py" << 'PYEOF'
import os
from cody import CodyClient

test_dir = os.environ["TEST_DIR"]

with CodyClient(workdir=test_dir) as client:
    result = client.tool("read_file", {"path": os.path.join(test_dir, "sample.txt")})
    has_content = "sync tool test content" in result.result
    print(f"TOOL_OK: {has_content}")
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_DIR="$TEST_DIR" python3 "$TEST_DIR/test_sync_tool.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 同步 `tool()` 正常读取文件

### 验证方法

```bash
grep "TOOL_OK: True" "$TEST_DIR/output.log" && echo "PASS: sync tool works" || echo "FAIL: sync tool failed"
```
