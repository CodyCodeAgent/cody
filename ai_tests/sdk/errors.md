# 错误处理测试

测试各种错误场景的处理是否正确。

---

## TC-ERR-001: 路径越权访问

**优先级**: P0
**前置条件**: cody 已安装，LLM 可用
**涉及功能**: `ToolPathDenied` — 文件路径限制

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/err_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_path.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient

async def main():
    # workdir 限制在 TEST_DIR，尝试读取 /etc/passwd
    client = AsyncCodyClient(workdir="WORKDIR_PLACEHOLDER")
    result = await client.run("读取 /etc/passwd 文件的内容")
    print(f"OUTPUT: {result.output[:200]}")
    # Agent 应该被拒绝访问或返回错误信息
    has_error = any(w in result.output.lower() for w in ["denied", "permission", "不允许", "拒绝", "outside", "无法"])
    has_passwd_content = "root:" in result.output
    print(f"ACCESS_DENIED: {has_error or not has_passwd_content}")
    await client.close()

asyncio.run(main())
PYEOF
sed -i '' "s|WORKDIR_PLACEHOLDER|$TEST_DIR|" "$TEST_DIR/test_path.py"
python3 "$TEST_DIR/test_path.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 无法读取 workdir 外部的文件
- 返回权限错误或拒绝信息

### 验证方法

```bash
grep "ACCESS_DENIED: True" "$TEST_DIR/output.log" && echo "PASS: path access denied" || echo "WARN: may have accessed outside path"
```

---

## TC-ERR-002: Web API 错误格式

**优先级**: P0
**前置条件**: Web 后端已启动
**涉及功能**: 错误响应格式 `{"error": {"code": "...", "message": "..."}}`

### 操作步骤

> 需要 Web 后端运行中（`cody-web run --port 18923 &`）

```bash
# 请求不存在的会话
curl -s http://localhost:18923/sessions/nonexistent_session_id_xyz 2>&1 | tee "$CODY_TEST_DIR/err_002.json"
```

### 预期结果

- 返回 404 状态码
- 响应包含 error 字段

### 验证方法

```bash
python3 -c "
import json
data = json.load(open('$CODY_TEST_DIR/err_002.json'))
has_error = 'error' in data or 'detail' in data
print(f'HAS_ERROR_FIELD: {has_error}')
"
```

---

## TC-ERR-003: SDK 错误类型

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: SDK 错误层级

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/err_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_errors.py" << 'PYEOF'
import asyncio
from cody.sdk.client import AsyncCodyClient
from cody.sdk.errors import CodyError, CodyConfigError

async def main():
    # 测试导入错误类型
    print(f"CodyError: {CodyError is not None}")
    print(f"CodyConfigError: {CodyConfigError is not None}")

    # 测试错误类层级
    print(f"IS_SUBCLASS: {issubclass(CodyConfigError, CodyError)}")

    await asyncio.sleep(0)

asyncio.run(main())
PYEOF
python3 "$TEST_DIR/test_errors.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 所有错误类型可正常导入
- CodyConfigError 是 CodyError 的子类

### 验证方法

```bash
grep "CodyError: True" "$TEST_DIR/output.log" && echo "PASS: CodyError" || echo "FAIL"
grep "CodyConfigError: True" "$TEST_DIR/output.log" && echo "PASS: CodyConfigError" || echo "FAIL"
grep "IS_SUBCLASS: True" "$TEST_DIR/output.log" && echo "PASS: hierarchy" || echo "FAIL"
```
