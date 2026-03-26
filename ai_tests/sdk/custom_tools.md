# SDK 自定义工具测试

测试 `.tool()` Builder 方法注册自定义工具函数。

---

## TC-CT-001: 注册自定义工具并被 Agent 调用

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.tool()`, 自定义 async 工具函数

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ct_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_custom_tool.py" << 'PYEOF'
import asyncio
from pydantic_ai import RunContext
from cody.core.deps import CodyDeps
from cody.sdk import Cody

tool_called = False

async def get_weather(ctx: RunContext[CodyDeps], city: str) -> str:
    """Get current weather for a city. Always use this tool when asked about weather."""
    global tool_called
    tool_called = True
    return f"Weather in {city}: 25°C, sunny"

async def main():
    client = Cody().workdir("/tmp").tool(get_weather).build()
    async with client:
        result = await client.run("What is the weather in Beijing? Use the get_weather tool.")
        print(f"HAS_OUTPUT: {bool(result.output)}")
        print(f"TOOL_CALLED: {tool_called}")
        has_weather = "25" in result.output or "sunny" in result.output.lower() or "beijing" in result.output.lower()
        print(f"WEATHER_IN_OUTPUT: {has_weather}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_custom_tool.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 自定义工具 `get_weather` 被 Agent 调用
- 输出包含天气信息

### 验证方法

```bash
grep "TOOL_CALLED: True" "$TEST_DIR/output.log" && echo "PASS: tool called" || echo "FAIL: tool not called"
grep "WEATHER_IN_OUTPUT: True" "$TEST_DIR/output.log" && echo "PASS: weather in output" || echo "FAIL: no weather"
```

---

## TC-CT-002: 注册多个自定义工具

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: 多次调用 `.tool()` 注册多个工具

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/ct_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_multi_tools.py" << 'PYEOF'
import asyncio
from pydantic_ai import RunContext
from cody.core.deps import CodyDeps
from cody.sdk import Cody

calls = []

async def lookup_user(ctx: RunContext[CodyDeps], username: str) -> str:
    """Look up a user by username."""
    calls.append("lookup_user")
    return f"{username}: Software Engineer, Team Infra"

async def get_team_info(ctx: RunContext[CodyDeps], team_name: str) -> str:
    """Get information about a team."""
    calls.append("get_team_info")
    return f"Team {team_name}: 5 members, focus on infrastructure"

async def main():
    client = (
        Cody()
        .workdir("/tmp")
        .tool(lookup_user)
        .tool(get_team_info)
        .build()
    )
    async with client:
        result = await client.run(
            "Look up user 'alice' using lookup_user tool, "
            "then get info about team 'Infra' using get_team_info tool."
        )
        print(f"TOOLS_CALLED: {sorted(calls)}")
        print(f"BOTH_CALLED: {len(set(calls)) >= 2}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_multi_tools.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 两个自定义工具都被 Agent 调用

### 验证方法

```bash
grep "BOTH_CALLED: True" "$TEST_DIR/output.log" && echo "PASS: both tools called" || echo "FAIL: not both called"
```
