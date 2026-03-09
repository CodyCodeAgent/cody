# 搜索工具测试

测试 Agent 的搜索能力（grep, glob, search_files）。

---

## TC-SEARCH-001: Grep 搜索内容

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `grep` 工具

### 操作步骤

1. 准备测试文件：
```bash
TEST_DIR="$CODY_TEST_DIR/search_001"
mkdir -p "$TEST_DIR/src"
cat > "$TEST_DIR/src/app.py" << 'EOF'
# TODO: add error handling
def process(data):
    result = transform(data)
    return result

# TODO: optimize performance
def transform(data):
    return [x * 2 for x in data]

# FIXME: this is a hack
def validate(data):
    return True
EOF

cat > "$TEST_DIR/src/utils.py" << 'EOF'
# TODO: add logging
def log(msg):
    print(msg)

def helper():
    pass
EOF
```

2. 让 Agent 搜索 TODO：
```bash
cody run --workdir "$TEST_DIR" "搜索项目中所有包含 TODO 的行，告诉我一共有几个 TODO" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 找到 3 个 TODO（app.py 中 2 个，utils.py 中 1 个）

### 验证方法

```bash
grep -i -E "3|三|three" "$TEST_DIR/output.log" && echo "PASS: found 3 TODOs" || echo "WARN: count may differ"
```

---

## TC-SEARCH-002: Glob 查找文件

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `glob` 工具

### 操作步骤

1. 准备文件结构：
```bash
TEST_DIR="$CODY_TEST_DIR/search_002"
mkdir -p "$TEST_DIR/src/components" "$TEST_DIR/src/utils" "$TEST_DIR/tests"
touch "$TEST_DIR/src/components/Button.tsx"
touch "$TEST_DIR/src/components/Input.tsx"
touch "$TEST_DIR/src/components/Modal.tsx"
touch "$TEST_DIR/src/utils/helpers.ts"
touch "$TEST_DIR/tests/test_button.py"
touch "$TEST_DIR/README.md"
```

2. 让 Agent 查找特定类型文件：
```bash
cody run --workdir "$TEST_DIR" "查找项目中所有 .tsx 文件，列出它们的路径" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 找到 3 个 .tsx 文件
- 提到 Button.tsx, Input.tsx, Modal.tsx

### 验证方法

```bash
grep -i "Button" "$TEST_DIR/output.log" && echo "PASS: found Button" || echo "FAIL: no Button"
grep -i "Input" "$TEST_DIR/output.log" && echo "PASS: found Input" || echo "FAIL: no Input"
grep -i "Modal" "$TEST_DIR/output.log" && echo "PASS: found Modal" || echo "FAIL: no Modal"
```

---

## TC-SEARCH-003: 搜索并修改

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `grep` + `edit_file` 组合

### 操作步骤

1. 准备文件：
```bash
TEST_DIR="$CODY_TEST_DIR/search_003"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/config.py" << 'EOF'
DEBUG = True
LOG_LEVEL = "DEBUG"
DATABASE_URL = "sqlite:///dev.db"
SECRET_KEY = "dev-secret-key"
EOF
```

2. 让 Agent 搜索并修改：
```bash
cody run --workdir "$TEST_DIR" "在 config.py 中把 DEBUG 改成 False，把 LOG_LEVEL 改成 WARNING"
```

### 预期结果

- `DEBUG = False`
- `LOG_LEVEL = "WARNING"`
- 其他配置不变

### 验证方法

```bash
grep "DEBUG = False" "$TEST_DIR/config.py" && echo "PASS: DEBUG is False" || echo "FAIL: DEBUG not changed"
grep 'LOG_LEVEL = "WARNING"' "$TEST_DIR/config.py" && echo "PASS: LOG_LEVEL is WARNING" || echo "FAIL: LOG_LEVEL not changed"
grep "DATABASE_URL" "$TEST_DIR/config.py" && echo "PASS: DB URL preserved" || echo "FAIL: DB URL lost"
grep "SECRET_KEY" "$TEST_DIR/config.py" && echo "PASS: SECRET preserved" || echo "FAIL: SECRET lost"
```
