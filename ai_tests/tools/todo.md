# Todo 工具测试

测试 `todo_write` 和 `todo_read` 工具。

---

## TC-TODO-001: todo_write 和 todo_read

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: `todo_write`, `todo_read` 工具

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/todo_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_todo.py" << 'PYEOF'
import asyncio
from cody.sdk import AsyncCodyClient

async def main():
    import json
    async with AsyncCodyClient(workdir="/tmp") as client:
        # Write todos (todos parameter expects a JSON string, not a list)
        write_result = await client.tool("todo_write", {
            "todos": json.dumps([
                {"content": "Fix login bug", "status": "pending"},
                {"content": "Write unit tests", "status": "in_progress"},
                {"content": "Deploy to staging", "status": "completed"},
            ])
        })
        print(f"WRITE_OK: {bool(write_result.result)}")

        # Read todos
        read_result = await client.tool("todo_read", {})
        has_todos = "login" in read_result.result.lower() or "Fix" in read_result.result
        print(f"READ_OK: {has_todos}")
        print(f"TODOS: {read_result.result[:300]}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_todo.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- todo_write 成功写入待办
- todo_read 返回已写入的待办列表

### 验证方法

```bash
grep "WRITE_OK: True" "$TEST_DIR/output.log" && echo "PASS: write ok" || echo "FAIL: write failed"
grep "READ_OK: True" "$TEST_DIR/output.log" && echo "PASS: read ok" || echo "FAIL: read failed"
```
