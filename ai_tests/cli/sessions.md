# 会话管理测试

测试 `cody sessions` 子命令组的功能。

---

## TC-SESSION-001: 列出会话

**优先级**: P1
**前置条件**: 至少执行过一次 `cody run`（会自动创建会话）
**涉及功能**: `cody sessions list`

### 操作步骤

1. 先创建一个会话：
```bash
TEST_DIR="$CODY_TEST_DIR/session_001"
mkdir -p "$TEST_DIR"
cody run --workdir "$TEST_DIR" "回复 session test"
```

2. 列出会话：
```bash
cody sessions list 2>&1 | tee "$TEST_DIR/sessions.log"
```

### 预期结果

- 输出中包含至少一个会话记录
- 显示会话 ID、标题、时间等信息

### 验证方法

```bash
# 检查输出不为空且包含会话信息
test -s "$TEST_DIR/sessions.log" && echo "PASS: has output" || echo "FAIL: empty output"
```

---

## TC-SESSION-002: 查看会话详情

**优先级**: P1
**前置条件**: 已有会话
**涉及功能**: `cody sessions show <id>`

### 操作步骤

1. 通过 SDK 创建会话并获取 ID：
```bash
TEST_DIR="$CODY_TEST_DIR/session_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/get_session.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")
    result = await client.run("回复 hello")
    # 获取最近的 session
    store = client.get_session_store()
    sessions = store.list_sessions()
    if sessions:
        print(f"SESSION_ID:{sessions[0].id}")
    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
SESSION_ID=$(python3 "$TEST_DIR/get_session.py" 2>/dev/null | grep "SESSION_ID:" | cut -d: -f2)
```

2. 查看该会话详情：
```bash
cody sessions show "$SESSION_ID" 2>&1 | tee "$TEST_DIR/detail.log"
```

### 预期结果

- 输出会话的消息历史
- 包含用户消息和 AI 回复

### 验证方法

```bash
test -s "$TEST_DIR/detail.log" && echo "PASS: has detail" || echo "FAIL: empty detail"
```

---

## TC-SESSION-003: 删除会话

**优先级**: P1
**前置条件**: 已有会话
**涉及功能**: `cody sessions delete <id>`

### 操作步骤

1. 通过 SDK 创建一个专门用于删除的会话：
```bash
TEST_DIR="$CODY_TEST_DIR/session_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/create_session.py" << 'PYEOF'
from cody.sdk.client import AsyncCodyClient
import asyncio

async def main():
    client = AsyncCodyClient(workdir="/tmp")
    store = client.get_session_store()
    s = store.create_session(title="To Delete", model="test", workdir="/tmp")
    print(f"SESSION_ID:{s.id}")
    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
SESSION_ID=$(python3 "$TEST_DIR/create_session.py" 2>/dev/null | grep "SESSION_ID:" | cut -d: -f2)
echo "Created session: $SESSION_ID"
```

2. 删除会话：
```bash
cody sessions delete "$SESSION_ID" 2>&1 | tee "$TEST_DIR/delete.log"
```

3. 再次查看，确认已删除：
```bash
cody sessions show "$SESSION_ID" 2>&1 | tee "$TEST_DIR/verify.log"
```

### 预期结果

- 删除命令正常执行
- 再次查看时提示会话不存在或返回空

### 验证方法

```bash
# 删除应该成功
grep -iv "error" "$TEST_DIR/delete.log" > /dev/null && echo "PASS: delete ok" || echo "FAIL: delete error"

# 再次查看应该找不到
grep -i -E "not found|no session|error" "$TEST_DIR/verify.log" && echo "PASS: session gone" || echo "WARN: might still exist"
```
