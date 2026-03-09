# CLI Chat 命令测试

测试 `cody chat` 的非交互方面（因为 chat 是交互式 REPL，AI 无法直接操作 stdin 多轮对话，所以这里测试可自动化验证的部分）。

> **注意**：由于 `cody chat` 是交互式命令，无法在非交互环境中完整测试。
> 以下用例侧重于验证命令的启动、参数解析和会话创建逻辑。
> 完整的多轮对话测试通过 SDK 用例覆盖。

---

## TC-CHAT-001: Chat 命令帮助信息

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `cody chat --help`

### 操作步骤

```bash
cody chat --help 2>&1 | tee /tmp/cody_chat_help.log
```

### 预期结果

- 显示帮助信息，包含选项说明

### 验证方法

```bash
grep -i "interactive" /tmp/cody_chat_help.log && echo "PASS: shows description" || echo "FAIL: no description"
grep -i "\-\-model" /tmp/cody_chat_help.log && echo "PASS: has --model" || echo "FAIL: no --model"
grep -i "\-\-session" /tmp/cody_chat_help.log && echo "PASS: has --session" || echo "FAIL: no --session"
grep -i "\-\-continue" /tmp/cody_chat_help.log && echo "PASS: has --continue" || echo "FAIL: no --continue"
grep -i "\-\-workdir" /tmp/cody_chat_help.log && echo "PASS: has --workdir" || echo "FAIL: no --workdir"
```

---

## TC-CHAT-002: Chat 通过 SDK 模拟多轮对话

**优先级**: P0
**前置条件**: cody 已安装，Python 可用
**涉及功能**: 多轮对话核心链路（通过 SDK 验证，等价于 chat 底层逻辑）

### 操作步骤

1. 创建测试脚本：
```bash
TEST_DIR="$CODY_TEST_DIR/chat_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_chat.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    client = AsyncCodyClient(workdir="/tmp")
    store = client.get_session_store()

    # 创建会话
    session = store.create_session(title="AI Test Chat", model="test", workdir="/tmp")
    print(f"SESSION_CREATED: {session.id}")

    # 第一轮对话
    result1 = await client.run("记住这个数字：42", session_id=session.id)
    print(f"TURN1_OK: {bool(result1.output)}")

    # 第二轮对话（验证上下文保持）
    result2 = await client.run("我刚才让你记住的数字是多少？", session_id=session.id)
    print(f"TURN2_OK: {bool(result2.output)}")

    # 检查第二轮是否记住了 42
    has_42 = "42" in result2.output
    print(f"CONTEXT_KEPT: {has_42}")

    await client.close()

asyncio.run(main())
PYEOF
```

2. 执行测试脚本：
```bash
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_chat.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 会话成功创建
- 两轮对话都返回结果
- 第二轮能回忆起数字 42（上下文保持）

### 验证方法

```bash
grep "SESSION_CREATED:" "$TEST_DIR/output.log" && echo "PASS: session created" || echo "FAIL: no session"
grep "TURN1_OK: True" "$TEST_DIR/output.log" && echo "PASS: turn 1 ok" || echo "FAIL: turn 1 failed"
grep "TURN2_OK: True" "$TEST_DIR/output.log" && echo "PASS: turn 2 ok" || echo "FAIL: turn 2 failed"
grep "CONTEXT_KEPT: True" "$TEST_DIR/output.log" && echo "PASS: context kept" || echo "FAIL: context lost"
```
