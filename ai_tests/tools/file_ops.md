# 文件操作工具测试

测试 Agent 的文件操作能力（read_file, write_file, edit_file, list_directory）。
这些测试通过 `cody run` 发出自然语言指令，验证 Agent 能否正确使用工具。

---

## TC-FILE-001: 创建文件

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `write_file` 工具

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/file_001"
mkdir -p "$TEST_DIR"
cody run --workdir "$TEST_DIR" "创建一个 config.json 文件，内容是 {\"name\": \"test\", \"version\": 1}"
```

### 预期结果

- `config.json` 被创建
- 内容是合法 JSON
- 包含 name 和 version 字段

### 验证方法

```bash
test -f "$TEST_DIR/config.json" && echo "PASS: file exists" || echo "FAIL: no file"
python3 -c "
import json
data = json.load(open('$CODY_TEST_DIR/file_001/config.json'))
print(f'VALID_JSON: True')
print(f'HAS_NAME: {\"name\" in data}')
print(f'HAS_VERSION: {\"version\" in data}')
" 2>&1 || echo "FAIL: invalid JSON"
```

---

## TC-FILE-002: 编辑现有文件

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `edit_file` 工具

### 操作步骤

1. 创建初始文件：
```bash
TEST_DIR="$CODY_TEST_DIR/file_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/app.py" << 'EOF'
def greet():
    return "hello"

def farewell():
    return "bye"
EOF
```

2. 让 Agent 修改文件：
```bash
cody run --workdir "$TEST_DIR" "修改 app.py，把 greet 函数的返回值改成 hello world，不要修改 farewell 函数"
```

### 预期结果

- `greet()` 返回 `"hello world"`
- `farewell()` 仍然返回 `"bye"`

### 验证方法

```bash
python3 -c "
import sys
sys.path.insert(0, '$CODY_TEST_DIR/file_002')
from app import greet, farewell
g = greet()
f = farewell()
print(f'GREET_OK: {\"hello world\" in g.lower()}')
print(f'FAREWELL_OK: {f == \"bye\"}')
"
```

---

## TC-FILE-003: 读取文件并回答问题

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `read_file` 工具

### 操作步骤

1. 创建一个包含特定信息的文件：
```bash
TEST_DIR="$CODY_TEST_DIR/file_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/data.txt" << 'EOF'
Project: Alpha
Author: Zhang Wei
Created: 2024-01-15
Status: Active
Description: A machine learning pipeline for text classification.
EOF
```

2. 让 Agent 读取并回答：
```bash
cody run --workdir "$TEST_DIR" "读取 data.txt，告诉我这个项目的作者是谁，只回复名字" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 输出包含 "Zhang Wei"

### 验证方法

```bash
grep -i "Zhang Wei" "$TEST_DIR/output.log" && echo "PASS: found author" || echo "FAIL: author not found"
```

---

## TC-FILE-004: 列出目录内容

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `list_directory` 工具

### 操作步骤

1. 创建目录结构：
```bash
TEST_DIR="$CODY_TEST_DIR/file_004"
mkdir -p "$TEST_DIR/src" "$TEST_DIR/tests" "$TEST_DIR/docs"
touch "$TEST_DIR/src/main.py" "$TEST_DIR/src/utils.py"
touch "$TEST_DIR/tests/test_main.py"
touch "$TEST_DIR/README.md"
```

2. 让 Agent 描述目录结构：
```bash
cody run --workdir "$TEST_DIR" "列出当前目录的文件结构，告诉我有几个 .py 文件" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 输出提到 3 个 .py 文件（main.py, utils.py, test_main.py）
- 或提到 src、tests 等目录

### 验证方法

```bash
grep -i -E "3|三|three" "$TEST_DIR/output.log" && echo "PASS: correct count" || echo "WARN: count may differ"
grep -i -E "main\.py|utils\.py|src" "$TEST_DIR/output.log" && echo "PASS: mentions files" || echo "FAIL: no file mention"
```

---

## TC-FILE-005: 创建嵌套目录结构

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `write_file` 工具（含目录创建）

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/file_005"
mkdir -p "$TEST_DIR"
cody run --workdir "$TEST_DIR" "创建以下目录结构和文件：src/models/user.py（包含 User 类，有 name 和 email 属性）和 src/models/__init__.py（从 user 导入 User）"
```

### 预期结果

- `src/models/user.py` 被创建，包含 User 类
- `src/models/__init__.py` 被创建，有 import 语句

### 验证方法

```bash
test -f "$TEST_DIR/src/models/user.py" && echo "PASS: user.py exists" || echo "FAIL: no user.py"
test -f "$TEST_DIR/src/models/__init__.py" && echo "PASS: __init__.py exists" || echo "FAIL: no __init__.py"
grep -i "class User" "$TEST_DIR/src/models/user.py" && echo "PASS: has User class" || echo "FAIL: no User class"
grep -i "name" "$TEST_DIR/src/models/user.py" && echo "PASS: has name attr" || echo "FAIL: no name"
grep -i "email" "$TEST_DIR/src/models/user.py" && echo "PASS: has email attr" || echo "FAIL: no email"
grep -i "import" "$TEST_DIR/src/models/__init__.py" && echo "PASS: has import" || echo "FAIL: no import"
```
