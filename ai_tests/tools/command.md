# 命令执行工具测试

测试 Agent 的命令执行能力（exec_command 工具）。

---

## TC-CMD-001: 执行简单命令

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `exec_command` 工具

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cmd_001"
mkdir -p "$TEST_DIR"
cody run --workdir "$TEST_DIR" "执行 python3 --version 命令，告诉我 Python 的版本号" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 输出包含 Python 版本号（如 3.10, 3.11, 3.12 等）

### 验证方法

```bash
grep -E "3\.[0-9]+" "$TEST_DIR/output.log" && echo "PASS: found Python version" || echo "FAIL: no version"
```

---

## TC-CMD-002: 执行命令并处理输出

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `exec_command` + 输出解析

### 操作步骤

1. 准备测试项目：
```bash
TEST_DIR="$CODY_TEST_DIR/cmd_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_math.py" << 'EOF'
import unittest

class TestMath(unittest.TestCase):
    def test_add(self):
        self.assertEqual(1 + 1, 2)

    def test_multiply(self):
        self.assertEqual(2 * 3, 6)

    def test_subtract(self):
        self.assertEqual(5 - 3, 2)

if __name__ == "__main__":
    unittest.main()
EOF
```

2. 让 Agent 运行测试：
```bash
cody run --workdir "$TEST_DIR" "运行 test_math.py 的单元测试，告诉我测试结果" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 执行了测试命令
- 报告 3 个测试通过

### 验证方法

```bash
grep -i -E "pass|通过|OK|3 test" "$TEST_DIR/output.log" && echo "PASS: tests reported" || echo "FAIL: no test report"
```

---

## TC-CMD-003: 安装依赖并运行

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `exec_command` 多步命令

### 操作步骤

1. 创建一个需要依赖的项目：
```bash
TEST_DIR="$CODY_TEST_DIR/cmd_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/app.py" << 'EOF'
"""Simple script that uses requests to check a URL status."""
import sys
try:
    import requests
    resp = requests.get("https://httpbin.org/status/200", timeout=10)
    print(f"STATUS: {resp.status_code}")
except ImportError:
    print("ERROR: requests not installed")
except Exception as e:
    print(f"ERROR: {e}")
EOF
```

2. 让 Agent 处理：
```bash
cody run --workdir "$TEST_DIR" "运行 app.py，如果缺少依赖就先安装，然后运行" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 识别到可能缺少 requests 库
- 尝试安装或直接运行（如果已安装）
- 最终输出 STATUS: 200 或相关结果

### 验证方法

```bash
# 宽松验证：Agent 尝试处理了这个任务
grep -i -E "status|requests|install|200|pip" "$TEST_DIR/output.log" && echo "PASS: handled dependency" || echo "FAIL: no action"
```

---

## TC-CMD-004: Git 操作

**优先级**: P1
**前置条件**: cody 已安装，git 可用
**涉及功能**: `exec_command` 执行 git 命令

### 操作步骤

1. 创建一个 git 仓库：
```bash
TEST_DIR="$CODY_TEST_DIR/cmd_004"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"
git init
git config user.email "test@test.com"
git config user.name "Test"
echo "hello" > README.md
git add . && git commit -m "init"
```

2. 让 Agent 查看 git 状态：
```bash
cody run --workdir "$TEST_DIR" "查看当前 git 仓库的状态和最近的 commit 信息" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 输出包含 git 状态信息
- 提到 "init" 或最近的 commit

### 验证方法

```bash
grep -i -E "init|clean|commit|branch" "$TEST_DIR/output.log" && echo "PASS: git info shown" || echo "FAIL: no git info"
```
