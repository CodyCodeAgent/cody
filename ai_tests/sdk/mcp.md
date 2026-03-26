# SDK MCP 集成测试

测试 MCP（Model Context Protocol）服务器配置与调用。

> **注意**：这些测试需要 MCP 服务器二进制可用（如 `npx`）。如不可用则 SKIP。

---

## TC-MCP-001: 配置 stdio MCP 服务器（构建验证）

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.mcp_stdio_server()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/mcp_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_mcp_config.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    # Just verify the builder doesn't crash — actual MCP server not required
    client = (
        Cody()
        .workdir("/tmp")
        .mcp_stdio_server(
            "test-server",
            command="echo",
            args=["hello"],
        )
        .build()
    )
    print(f"BUILD_OK: True")
    # Don't auto_start — we just test config parsing
    cfg = client._config
    has_mcp = len(cfg.mcp.servers) > 0
    print(f"MCP_CONFIGURED: {has_mcp}")
    server_name = cfg.mcp.servers[0].name if cfg.mcp.servers else ""
    print(f"SERVER_NAME: {server_name}")
    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_mcp_config.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Builder 正确解析 MCP 配置
- 不报错

### 验证方法

```bash
grep "BUILD_OK: True" "$TEST_DIR/output.log" && echo "PASS: build ok" || echo "FAIL: build failed"
grep "MCP_CONFIGURED: True" "$TEST_DIR/output.log" && echo "PASS: mcp configured" || echo "FAIL: mcp not configured"
grep "SERVER_NAME: test-server" "$TEST_DIR/output.log" && echo "PASS: server name" || echo "FAIL: wrong name"
```

---

## TC-MCP-002: 配置 HTTP MCP 服务器（构建验证）

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.mcp_http_server()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/mcp_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_mcp_http.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    client = (
        Cody()
        .workdir("/tmp")
        .mcp_http_server(
            "feishu",
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer test"},
        )
        .build()
    )
    print(f"BUILD_OK: True")
    cfg = client._config
    server = cfg.mcp.servers[0] if cfg.mcp.servers else None
    print(f"SERVER_NAME: {server.name if server else 'NONE'}")
    print(f"TRANSPORT: {server.transport if server else 'NONE'}")
    await client.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_mcp_http.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- HTTP MCP 服务器配置正确解析

### 验证方法

```bash
grep "BUILD_OK: True" "$TEST_DIR/output.log" && echo "PASS: build ok" || echo "FAIL: build failed"
grep "SERVER_NAME: feishu" "$TEST_DIR/output.log" && echo "PASS: server name" || echo "FAIL: wrong name"
grep "TRANSPORT: http" "$TEST_DIR/output.log" && echo "PASS: http transport" || echo "FAIL: wrong transport"
```
