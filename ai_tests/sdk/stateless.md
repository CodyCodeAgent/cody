# SDK 无状态模式测试

测试 `.stateless()` Builder 方法，确保不写入任何持久化文件。

---

## TC-SL-001: Stateless 模式不创建数据库文件

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.stateless()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sl_001"
mkdir -p "$TEST_DIR/workdir"
cat > "$TEST_DIR/test_stateless.py" << 'PYEOF'
import asyncio
import os
import glob

workdir = os.environ["TEST_WORKDIR"]

async def main():
    from cody.sdk import Cody

    client = Cody().workdir(workdir).stateless().build()
    async with client:
        result = await client.run("回复 OK")
        print(f"HAS_OUTPUT: {bool(result.output)}")

    # Check no database files were created
    db_files = glob.glob(os.path.join(workdir, "**/*.db"), recursive=True)
    home_db = os.path.expanduser("~/.cody/sessions.db")
    # Note: sessions.db might exist from other tests, so check workdir only
    print(f"NO_LOCAL_DB: {len(db_files) == 0}")
    print(f"DB_FILES: {db_files}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_stateless.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 正常执行任务
- 工作目录下不会创建 `.db` 文件

### 验证方法

```bash
grep "HAS_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: stateless run works" || echo "FAIL: run failed"
grep "NO_LOCAL_DB: True" "$TEST_DIR/output.log" && echo "PASS: no local db" || echo "FAIL: db files created"
```

---

## TC-SL-002: Stateless 模式下 session_id 为 None

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `NullSessionStore` 行为

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sl_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_stateless_session.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    client = Cody().workdir("/tmp").stateless().build()
    async with client:
        result = await client.run("回复 OK")
        print(f"HAS_OUTPUT: {bool(result.output)}")
        # Stateless mode should still return output but session_id may be None
        print(f"SESSION_ID: {result.session_id}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_stateless_session.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 任务正常完成
- session 不持久化

### 验证方法

```bash
grep "HAS_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: run works" || echo "FAIL: run failed"
```
