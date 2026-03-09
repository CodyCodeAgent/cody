# SDK 基本功能测试

测试 Python SDK (`AsyncCodyClient`) 的核心功能。

---

## TC-SDK-001: 基本 run 执行

**优先级**: P0
**前置条件**: cody 已安装为 Python 包
**涉及功能**: `AsyncCodyClient.run()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sdk_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_run.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")
    result = await client.run("回复两个字：收到")
    print(f"HAS_OUTPUT: {bool(result.output)}")
    print(f"OUTPUT: {result.output}")
    print(f"HAS_USAGE: {result.usage is not None}")
    if result.usage:
        print(f"TOKENS: {result.usage.total_tokens}")
    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_run.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- `result.output` 非空，包含 "收到" 相关内容
- `result.usage` 存在，token 数 > 0

### 验证方法

```bash
grep "HAS_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: has output" || echo "FAIL: no output"
grep "HAS_USAGE: True" "$TEST_DIR/output.log" && echo "PASS: has usage" || echo "FAIL: no usage"
```

---

## TC-SDK-002: Builder 模式创建客户端

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `Cody()` Builder pattern

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sdk_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_builder.py" << 'PYEOF'
import asyncio
from cody import Cody

async def main():
    client = Cody().workdir("/tmp").build()
    result = await client.run("回复 OK")
    print(f"BUILDER_OK: {bool(result.output)}")
    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_builder.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Builder 模式正常构建客户端
- 能成功执行任务

### 验证方法

```bash
grep "BUILDER_OK: True" "$TEST_DIR/output.log" && echo "PASS: builder works" || echo "FAIL: builder failed"
```

---

## TC-SDK-003: 会话管理

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `SessionStore` 通过 SDK 访问

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sdk_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_sessions.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")
    store = client.get_session_store()

    # 创建会话
    session = store.create_session(title="SDK Test", model="test", workdir="/tmp")
    print(f"CREATED: {session.id}")

    # 列出会话
    sessions = store.list_sessions()
    found = any(s.id == session.id for s in sessions)
    print(f"LISTED: {found}")

    # 获取详情
    detail = store.get_session(session.id)
    print(f"GOT_DETAIL: {detail is not None}")
    print(f"TITLE_MATCH: {detail.title == 'SDK Test'}")

    # 删除
    store.delete_session(session.id)
    after_delete = store.get_session(session.id)
    print(f"DELETED: {after_delete is None}")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_sessions.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 会话 CRUD 全部正常

### 验证方法

```bash
grep "CREATED:" "$TEST_DIR/output.log" && echo "PASS: create" || echo "FAIL: create"
grep "LISTED: True" "$TEST_DIR/output.log" && echo "PASS: list" || echo "FAIL: list"
grep "GOT_DETAIL: True" "$TEST_DIR/output.log" && echo "PASS: get" || echo "FAIL: get"
grep "TITLE_MATCH: True" "$TEST_DIR/output.log" && echo "PASS: title" || echo "FAIL: title"
grep "DELETED: True" "$TEST_DIR/output.log" && echo "PASS: delete" || echo "FAIL: delete"
```

---

## TC-SDK-004: 工具调用验证

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: Agent 通过 SDK 调用工具（写文件）

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/sdk_004"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_tools.py" << 'PYEOF'
import asyncio
import os
from cody.sdk.client import AsyncCodyClient

async def main():
    workdir = os.environ.get("TEST_WORKDIR", "/tmp/sdk_tool_test")
    os.makedirs(workdir, exist_ok=True)

    client = AsyncCodyClient(workdir=workdir)
    result = await client.run("在当前目录创建 greeting.txt，内容写 Hello from SDK")

    # 检查文件是否被创建
    filepath = os.path.join(workdir, "greeting.txt")
    file_exists = os.path.isfile(filepath)
    print(f"FILE_CREATED: {file_exists}")

    if file_exists:
        content = open(filepath).read()
        has_hello = "hello" in content.lower() or "Hello" in content
        print(f"CONTENT_OK: {has_hello}")

    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$CODY_TEST_DIR/sdk_004_work" python3 "$TEST_DIR/test_tools.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 通过工具创建了文件
- 文件内容包含 Hello

### 验证方法

```bash
grep "FILE_CREATED: True" "$TEST_DIR/output.log" && echo "PASS: file created" || echo "FAIL: no file"
grep "CONTENT_OK: True" "$TEST_DIR/output.log" && echo "PASS: content ok" || echo "FAIL: wrong content"
```
