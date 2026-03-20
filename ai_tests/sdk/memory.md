# SDK 跨任务记忆测试

测试 Project Memory 功能：add / get / clear 记忆，以及 `save_memory` 工具。

---

## TC-MEM-001: 记忆 CRUD 操作

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `add_memory()`, `get_memory()`, `clear_memory()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/mem_001"
WORK_DIR="$TEST_DIR/workspace"
mkdir -p "$WORK_DIR"
cat > "$TEST_DIR/test_memory_crud.py" << 'PYEOF'
import asyncio
import os
from cody.sdk.client import AsyncCodyClient

async def main():
    workdir = os.environ.get("TEST_WORKDIR", "/tmp/mem_test")
    os.makedirs(workdir, exist_ok=True)

    client = AsyncCodyClient(workdir=workdir)

    # 添加记忆
    await client.add_memory("conventions", "使用 snake_case 命名变量")
    await client.add_memory("patterns", "使用工厂模式创建对象")
    await client.add_memory("issues", "注意 N+1 查询问题")
    await client.add_memory("decisions", "选用 PostgreSQL 作为主数据库")
    print("ADD_OK: True")

    # 获取记忆
    memories = await client.get_memory()
    print(f"HAS_CONVENTIONS: {'conventions' in memories}")
    print(f"HAS_PATTERNS: {'patterns' in memories}")
    print(f"HAS_ISSUES: {'issues' in memories}")
    print(f"HAS_DECISIONS: {'decisions' in memories}")

    # 检查内容
    conv_entries = memories.get("conventions", [])
    has_snake = any("snake_case" in e.get("content", "") for e in conv_entries)
    print(f"CONTENT_MATCH: {has_snake}")

    # 清除记忆
    await client.clear_memory()
    after_clear = await client.get_memory()
    total_after = sum(len(v) for v in after_clear.values())
    print(f"CLEARED: {total_after == 0}")

    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
TEST_WORKDIR="$WORK_DIR" python3 "$TEST_DIR/test_memory_crud.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 四个分类的记忆均可添加和读取
- `clear_memory()` 后记忆为空

### 验证方法

```bash
grep "ADD_OK: True" "$TEST_DIR/output.log" && echo "PASS: add memory" || echo "FAIL: add failed"
grep "HAS_CONVENTIONS: True" "$TEST_DIR/output.log" && echo "PASS: conventions" || echo "FAIL: no conventions"
grep "HAS_PATTERNS: True" "$TEST_DIR/output.log" && echo "PASS: patterns" || echo "FAIL: no patterns"
grep "CONTENT_MATCH: True" "$TEST_DIR/output.log" && echo "PASS: content match" || echo "FAIL: content mismatch"
grep "CLEARED: True" "$TEST_DIR/output.log" && echo "PASS: cleared" || echo "FAIL: not cleared"
```

---

## TC-MEM-002: AI 通过 save_memory 工具保存记忆

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `save_memory` 工具 + AI 自动调用

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/mem_002"
WORK_DIR="$TEST_DIR/workspace"
mkdir -p "$WORK_DIR"
cat > "$TEST_DIR/test_save_memory_tool.py" << 'PYEOF'
import asyncio
import os
from cody.sdk.client import AsyncCodyClient

async def main():
    workdir = os.environ.get("TEST_WORKDIR", "/tmp/mem_tool_test")
    os.makedirs(workdir, exist_ok=True)

    client = AsyncCodyClient(workdir=workdir)

    # 让 AI 执行任务并主动保存记忆
    result = await client.run(
        "请使用 save_memory 工具保存一条记忆，分类为 conventions，"
        "内容为「Python 项目使用 pytest 作为测试框架」"
    )
    print(f"RUN_OK: {bool(result.output)}")

    # 检查记忆是否被保存
    memories = await client.get_memory()
    conv = memories.get("conventions", [])
    has_pytest = any("pytest" in e.get("content", "") for e in conv)
    print(f"MEMORY_SAVED: {has_pytest}")
    print(f"ENTRY_COUNT: {len(conv)}")

    # 清理
    await client.clear_memory()
    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
TEST_WORKDIR="$WORK_DIR" python3 "$TEST_DIR/test_save_memory_tool.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- AI 成功调用 `save_memory` 工具
- 记忆存储中出现包含 "pytest" 的条目

### 验证方法

```bash
grep "RUN_OK: True" "$TEST_DIR/output.log" && echo "PASS: run completed" || echo "FAIL: run failed"
grep "MEMORY_SAVED: True" "$TEST_DIR/output.log" && echo "PASS: memory saved via tool" || echo "FAIL: memory not saved"
```

---

## TC-MEM-003: 记忆带 confidence 和 tags

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: `add_memory()` 的 confidence 和 tags 参数

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/mem_003"
WORK_DIR="$TEST_DIR/workspace"
mkdir -p "$WORK_DIR"
cat > "$TEST_DIR/test_memory_metadata.py" << 'PYEOF'
import asyncio
import os
from cody.sdk.client import AsyncCodyClient

async def main():
    workdir = os.environ.get("TEST_WORKDIR", "/tmp/mem_meta_test")
    os.makedirs(workdir, exist_ok=True)

    client = AsyncCodyClient(workdir=workdir)

    # 添加带 confidence 和 tags 的记忆
    await client.add_memory(
        "decisions",
        "选用 Redis 作为缓存层",
        confidence=0.9,
        tags=["cache", "infrastructure"],
    )

    memories = await client.get_memory()
    decisions = memories.get("decisions", [])

    if decisions:
        entry = decisions[0]
        print(f"HAS_CONFIDENCE: {'confidence' in entry}")
        print(f"CONFIDENCE_VALUE: {entry.get('confidence', 0)}")
        print(f"HAS_TAGS: {'tags' in entry}")
        print(f"TAGS: {entry.get('tags', [])}")
    else:
        print("NO_ENTRIES: True")

    await client.clear_memory()
    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
TEST_WORKDIR="$WORK_DIR" python3 "$TEST_DIR/test_memory_metadata.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 记忆条目包含 confidence 和 tags 字段
- 值与传入参数一致

### 验证方法

```bash
grep "HAS_CONFIDENCE: True" "$TEST_DIR/output.log" && echo "PASS: has confidence" || echo "FAIL: no confidence"
grep "HAS_TAGS: True" "$TEST_DIR/output.log" && echo "PASS: has tags" || echo "FAIL: no tags"
```
