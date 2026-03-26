# SDK 自定义 Prompt 测试

测试 `.system_prompt()` 和 `.extra_system_prompt()` 对 Agent 行为的影响。

---

## TC-CP-001: 替换系统 Prompt

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.system_prompt()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cp_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_system_prompt.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    client = (
        Cody()
        .workdir("/tmp")
        .system_prompt(
            "You are a pirate assistant. You must always speak like a pirate. "
            "Use words like 'Ahoy', 'matey', 'treasure', 'ye', 'arr'."
        )
        .build()
    )
    async with client:
        result = await client.run("Say hello and introduce yourself briefly")
        output_lower = result.output.lower()
        has_pirate = any(w in output_lower for w in ["ahoy", "matey", "treasure", "arr", "ye"])
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"HAS_PIRATE_WORDS: {has_pirate}")
        print(f"OUTPUT_PREVIEW: {result.output[:200]}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_system_prompt.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 使用海盗风格说话
- 输出包含海盗风格词汇

### 验证方法

```bash
grep "HAS_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: has output" || echo "FAIL: no output"
grep "HAS_PIRATE_WORDS: True" "$TEST_DIR/output.log" && echo "PASS: pirate style" || echo "FAIL: no pirate words"
```

---

## TC-CP-002: 追加额外 Prompt

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.extra_system_prompt()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cp_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_extra_prompt.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    client = (
        Cody()
        .workdir("/tmp")
        .extra_system_prompt(
            "IMPORTANT: At the end of every response, you must append the exact line: "
            "SIGNATURE: ExtraPromptWorks"
        )
        .build()
    )
    async with client:
        result = await client.run("Say hello in one sentence")
        has_signature = "SIGNATURE: ExtraPromptWorks" in result.output
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"HAS_SIGNATURE: {has_signature}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_extra_prompt.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 响应中包含指定签名，证明 extra prompt 生效

### 验证方法

```bash
grep "HAS_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: has output" || echo "FAIL: no output"
grep "HAS_SIGNATURE: True" "$TEST_DIR/output.log" && echo "PASS: extra prompt works" || echo "FAIL: no signature"
```
