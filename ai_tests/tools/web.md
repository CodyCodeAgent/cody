# Web 工具测试

测试 `webfetch` 和 `websearch` 工具。

> **注意**：这些测试需要网络连接。如无网络则 SKIP。

---

## TC-WEB-001: webfetch 抓取网页

**优先级**: P2
**前置条件**: cody 已安装, 有网络连接
**涉及功能**: `webfetch` 工具

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/web_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_webfetch.py" << 'PYEOF'
import asyncio
from cody.sdk import AsyncCodyClient

async def main():
    async with AsyncCodyClient(workdir="/tmp") as client:
        result = await client.tool("webfetch", {"url": "https://httpbin.org/get"})
        has_content = bool(result.result) and len(result.result) > 50
        has_httpbin = "httpbin" in result.result.lower() or "origin" in result.result.lower()
        print(f"HAS_CONTENT: {has_content}")
        print(f"HAS_HTTPBIN: {has_httpbin}")
        print(f"CONTENT_LEN: {len(result.result)}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_webfetch.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 成功抓取 httpbin.org 内容
- 返回包含 JSON 数据

### 验证方法

```bash
grep "HAS_CONTENT: True" "$TEST_DIR/output.log" && echo "PASS: has content" || echo "FAIL: no content"
grep "HAS_HTTPBIN: True" "$TEST_DIR/output.log" && echo "PASS: httpbin ok" || echo "FAIL: wrong content"
```

---

## TC-WEB-002: websearch 搜索

**优先级**: P2
**前置条件**: cody 已安装, 有网络连接
**涉及功能**: `websearch` 工具

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/web_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_websearch.py" << 'PYEOF'
import asyncio
from cody.sdk import AsyncCodyClient

async def main():
    async with AsyncCodyClient(workdir="/tmp") as client:
        result = await client.tool("websearch", {"query": "Python programming language"})
        has_result = bool(result.result) and len(result.result) > 20
        has_python = "python" in result.result.lower()
        print(f"HAS_RESULT: {has_result}")
        print(f"HAS_PYTHON: {has_python}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_websearch.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 搜索返回与 Python 相关的结果

### 验证方法

```bash
grep "HAS_RESULT: True" "$TEST_DIR/output.log" && echo "PASS: has result" || echo "FAIL: no result"
grep "HAS_PYTHON: True" "$TEST_DIR/output.log" && echo "PASS: relevant results" || echo "FAIL: irrelevant"
```
