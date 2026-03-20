# SDK 用户主动输入测试

测试 Proactive User Input 功能：`inject_user_input()` 在 Agent 运行中注入用户消息。

---

## TC-UI-001: inject_user_input 基本功能

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `AsyncCodyClient.inject_user_input()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ui_001"
WORK_DIR="$TEST_DIR/workspace"
mkdir -p "$WORK_DIR"
cat > "$TEST_DIR/test_user_input.py" << 'PYEOF'
import asyncio
import os
from cody.sdk.client import AsyncCodyClient

async def main():
    workdir = os.environ.get("TEST_WORKDIR", "/tmp/ui_test")
    os.makedirs(workdir, exist_ok=True)

    client = AsyncCodyClient(workdir=workdir)

    # 启动一个需要工具调用的长任务，然后注入用户消息
    chunks = []
    injected = False

    async for chunk in client.stream(
        "创建一个 hello.txt 文件，内容写 Hello World，然后等我指示下一步"
    ):
        chunks.append(chunk)
        print(f"EVENT: {chunk.type}")

        # 在第一个 tool_result 之后注入用户消息
        if chunk.type == "tool_result" and not injected:
            await client.inject_user_input("好的，再创建一个 bye.txt，内容写 Goodbye")
            injected = True
            print("INJECTED: True")

    types = [c.type for c in chunks]
    print(f"CHUNK_TYPES: {sorted(set(types))}")
    print(f"HAS_EVENTS: {len(chunks) > 0}")

    # 检查第一个文件是否创建
    hello_exists = os.path.isfile(os.path.join(workdir, "hello.txt"))
    print(f"HELLO_EXISTS: {hello_exists}")

    # 检查注入的消息是否触发了第二个文件创建
    bye_exists = os.path.isfile(os.path.join(workdir, "bye.txt"))
    print(f"BYE_EXISTS: {bye_exists}")

    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
TEST_WORKDIR="$WORK_DIR" timeout 120 python3 "$TEST_DIR/test_user_input.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 创建 hello.txt
- 用户输入被注入后，Agent 继续执行并创建 bye.txt
- 流式输出中包含 `user_input_received` 事件（如果 core 发出该事件）

### 验证方法

```bash
grep "HELLO_EXISTS: True" "$TEST_DIR/output.log" && echo "PASS: hello.txt created" || echo "FAIL: no hello.txt"
grep "INJECTED: True" "$TEST_DIR/output.log" && echo "PASS: input injected" || echo "FAIL: not injected"
grep "BYE_EXISTS: True" "$TEST_DIR/output.log" && echo "PASS: bye.txt created (input effective)" || echo "FAIL: no bye.txt (input may not have been processed)"
```

---

## TC-UI-002: inject_user_input 无任务运行时不报错

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `inject_user_input()` 在空闲时不崩溃

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ui_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_ui_idle.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")

    # 没有正在运行的任务时注入消息
    try:
        await client.inject_user_input("测试消息")
        print("NO_ERROR: True")
    except Exception as e:
        print(f"ERROR: {e}")
        print("NO_ERROR: False")

    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
python3 "$TEST_DIR/test_ui_idle.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 不应抛出异常
- 消息被静默忽略或排队

### 验证方法

```bash
grep "NO_ERROR: True" "$TEST_DIR/output.log" && echo "PASS: no error on idle inject" || echo "FAIL: error occurred"
```

---

## TC-UI-003: 流式输出中 user_input_received 事件

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: `UserInputReceivedEvent` 出现在流式输出中

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ui_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_ui_event.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")

    chunks = []
    injected = False

    async for chunk in client.stream("写一篇 200 字的关于编程的文章"):
        chunks.append(chunk)
        # 收到第一个 text_delta 后注入
        if chunk.type == "text_delta" and not injected:
            await client.inject_user_input("请用英文写")
            injected = True

    types = [c.type for c in chunks]
    has_ui_event = "user_input_received" in types
    print(f"HAS_UI_EVENT: {has_ui_event}")
    print(f"INJECTED: {injected}")
    print(f"TOTAL_CHUNKS: {len(chunks)}")

    await client.close()

asyncio.run(main())
PYEOF
cd "$CODY_PROJECT_DIR"
timeout 120 python3 "$TEST_DIR/test_ui_event.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 输入注入后，流式事件中可能出现 `user_input_received` 事件
- 注入的消息在下一个 node 边界被处理

### 验证方法

```bash
grep "INJECTED: True" "$TEST_DIR/output.log" && echo "PASS: injection attempted" || echo "FAIL: no injection"
# user_input_received 是可选验证（取决于 node 边界时机）
grep "HAS_UI_EVENT:" "$TEST_DIR/output.log" && echo "INFO: UI event status recorded" || echo "INFO: no UI event check"
```
