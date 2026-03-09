# CLI Run 命令测试

测试 `cody run` 命令的核心功能。

---

## TC-CLI-001: 基本任务执行

**优先级**: P0
**前置条件**: cody 已安装，API Key 已配置
**涉及功能**: `cody run` 基本执行链路

### 操作步骤

1. 创建测试目录并进入：
```bash
TEST_DIR="$CODY_TEST_DIR/cli_run_001"
mkdir -p "$TEST_DIR" && cd "$TEST_DIR"
```

2. 执行一个简单的文件创建任务：
```bash
cody run --workdir "$TEST_DIR" "创建一个 hello.py 文件，内容是打印 hello world"
```

### 预期结果

- 命令正常退出（exit code 0）
- `hello.py` 文件被创建
- 文件内容包含 `print` 和 `hello` 相关代码

### 验证方法

```bash
# 检查文件存在
test -f "$TEST_DIR/hello.py" && echo "PASS: file exists" || echo "FAIL: file not found"

# 检查内容相关性
grep -i "print" "$TEST_DIR/hello.py" && echo "PASS: has print" || echo "FAIL: no print"
grep -i "hello" "$TEST_DIR/hello.py" && echo "PASS: has hello" || echo "FAIL: no hello"

# 检查文件可执行
python3 "$TEST_DIR/hello.py" && echo "PASS: runs ok" || echo "FAIL: runtime error"
```

---

## TC-CLI-002: 指定工作目录

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `--workdir` 参数

### 操作步骤

1. 创建目标目录：
```bash
TEST_DIR="$CODY_TEST_DIR/cli_run_002"
mkdir -p "$TEST_DIR"
```

2. 从其他位置执行，指定 workdir：
```bash
cd /tmp
cody run --workdir "$TEST_DIR" "在当前目录创建一个 README.md 文件，内容写 Test Project"
```

### 预期结果

- `README.md` 创建在 `$TEST_DIR` 下，而非 `/tmp` 下

### 验证方法

```bash
test -f "$TEST_DIR/README.md" && echo "PASS: file in workdir" || echo "FAIL: file not in workdir"
test ! -f /tmp/README.md && echo "PASS: not in /tmp" || echo "WARN: also created in /tmp"
```

---

## TC-CLI-003: Verbose 模式

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: `-v` / `--verbose` 参数

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cli_run_003"
mkdir -p "$TEST_DIR"
cody run -v --workdir "$TEST_DIR" "回复一句 hello" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 输出中包含额外调试信息（如 Model、Workdir 等）

### 验证方法

```bash
grep -i "model" "$TEST_DIR/output.log" && echo "PASS: shows model info" || echo "FAIL: no model info"
```

---

## TC-CLI-004: 无 prompt 提示

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: 参数校验

### 操作步骤

```bash
cody run 2>&1 | tee /tmp/cody_no_prompt.log
```

### 预期结果

- 不会崩溃
- 输出提示信息，告知需要提供 prompt

### 验证方法

```bash
grep -i -E "prompt|example|provide" /tmp/cody_no_prompt.log && echo "PASS: shows hint" || echo "FAIL: no hint"
```

---

## TC-CLI-005: 代码修改任务

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: Agent 读写文件的完整链路

### 操作步骤

1. 准备一个有 bug 的文件：
```bash
TEST_DIR="$CODY_TEST_DIR/cli_run_005"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/calc.py" << 'EOF'
def add(a, b):
    return a - b  # bug: should be a + b

def multiply(a, b):
    return a * b

if __name__ == "__main__":
    print(add(2, 3))
    print(multiply(4, 5))
EOF
```

2. 让 cody 修复 bug：
```bash
cody run --workdir "$TEST_DIR" "calc.py 中的 add 函数有 bug，请修复它"
```

### 预期结果

- `add` 函数的 `return a - b` 被改为 `return a + b`
- `multiply` 函数不受影响

### 验证方法

```bash
# 运行修复后的代码，add(2,3) 应该返回 5
RESULT=$(python3 "$TEST_DIR/calc.py" | head -1)
if [ "$RESULT" = "5" ]; then
    echo "PASS: add(2,3) = 5"
else
    echo "FAIL: add(2,3) = $RESULT, expected 5"
fi

# multiply 应该不受影响
RESULT2=$(python3 "$TEST_DIR/calc.py" | tail -1)
if [ "$RESULT2" = "20" ]; then
    echo "PASS: multiply(4,5) = 20"
else
    echo "FAIL: multiply(4,5) = $RESULT2, expected 20"
fi
```

---

## TC-CLI-006: 多文件任务

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: Agent 创建多个文件

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/cli_run_006"
mkdir -p "$TEST_DIR"
cody run --workdir "$TEST_DIR" "创建一个简单的 Python 项目结构：main.py 作为入口，utils.py 包含一个 greet(name) 函数，main.py 调用 greet"
```

### 预期结果

- `main.py` 和 `utils.py` 都被创建
- `main.py` 中 import 了 `utils`
- 运行 `main.py` 不报错

### 验证方法

```bash
test -f "$TEST_DIR/main.py" && echo "PASS: main.py exists" || echo "FAIL: no main.py"
test -f "$TEST_DIR/utils.py" && echo "PASS: utils.py exists" || echo "FAIL: no utils.py"
grep -i "import" "$TEST_DIR/main.py" && echo "PASS: has import" || echo "FAIL: no import"
grep -i "def greet" "$TEST_DIR/utils.py" && echo "PASS: has greet func" || echo "FAIL: no greet"
cd "$TEST_DIR" && python3 main.py && echo "PASS: runs ok" || echo "FAIL: runtime error"
```
