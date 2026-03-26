# SDK LSP 集成测试

测试 LSP（Language Server Protocol）配置。

> **注意**：需要对应 LSP 服务器已安装（如 `pylsp`）。未安装时 SKIP。

---

## TC-LSP-001: LSP 语言配置

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: `CodyBuilder.lsp_languages()`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/lsp_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_lsp_config.py" << 'PYEOF'
import asyncio
from cody.sdk import Cody

async def main():
    # Test custom LSP languages config
    client = (
        Cody()
        .workdir("/tmp")
        .lsp_languages(["python"])
        .build()
    )
    print(f"BUILD_OK: True")
    languages = client._config.lsp.languages
    print(f"LANGUAGES: {languages}")
    print(f"PYTHON_ONLY: {languages == ['python']}")
    await client.close()

    # Test empty LSP (disabled)
    client2 = Cody().workdir("/tmp").lsp_languages([]).build()
    print(f"EMPTY_OK: {client2._config.lsp.languages == []}")
    await client2.close()

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
python3 "$TEST_DIR/test_lsp_config.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- LSP 语言列表正确配置
- 空列表禁用 LSP

### 验证方法

```bash
grep "PYTHON_ONLY: True" "$TEST_DIR/output.log" && echo "PASS: python only" || echo "FAIL: wrong languages"
grep "EMPTY_OK: True" "$TEST_DIR/output.log" && echo "PASS: empty disables" || echo "FAIL: not disabled"
```

---

## TC-LSP-002: LSP diagnostics 便捷方法

**优先级**: P2
**前置条件**: cody 已安装, `pylsp` 已安装
**涉及功能**: `AsyncCodyClient.lsp_diagnostics()`

### 操作步骤

```bash
# Check if pylsp is available
which pylsp > /dev/null 2>&1 || { echo "SKIP: pylsp not installed"; exit 0; }

TEST_DIR="$CODY_TEST_DIR/lsp_002"
mkdir -p "$TEST_DIR/workdir"
cat > "$TEST_DIR/workdir/buggy.py" << 'PYEOF'
import os
import sys  # unused import

def foo():
    x = 1
    return y  # undefined name
PYEOF

cat > "$TEST_DIR/test_lsp_diag.py" << 'PYEOF'
import asyncio
import os
from cody.sdk import Cody

async def main():
    workdir = os.environ["TEST_WORKDIR"]
    client = Cody().workdir(workdir).lsp_languages(["python"]).build()
    async with client:
        await client.start_lsp()
        diags = await client.lsp_diagnostics(os.path.join(workdir, "buggy.py"))
        print(f"HAS_DIAGS: {bool(diags)}")
        print(f"DIAGS: {diags[:300]}")

asyncio.run(main())
PYEOF
cd /Users/bytedance/GC/GitHub/cody
TEST_WORKDIR="$TEST_DIR/workdir" python3 "$TEST_DIR/test_lsp_diag.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- LSP 返回诊断信息（如未使用的 import）

### 验证方法

```bash
grep "HAS_DIAGS: True" "$TEST_DIR/output.log" && echo "PASS: got diagnostics" || echo "FAIL: no diagnostics"
```
