# 子 Agent 测试

测试 Agent 的子 Agent 编排能力（spawn_agent, get_agent_status, kill_agent）。

---

## TC-AGENT-001: 生成并查询子 Agent

**优先级**: P0
**前置条件**: cody 已安装，LLM 可用
**涉及功能**: `spawn_agent` + `get_agent_status`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/agent_001"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test.py" << 'EOF'
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
EOF
cody run --workdir "$TEST_DIR" "使用子 Agent 分析 test.py 的代码结构，告诉我它包含哪些函数" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 尝试使用 spawn_agent 或直接分析
- 输出提到 add 和 subtract 函数

### 验证方法

```bash
grep -i "add" "$TEST_DIR/output.log" && echo "PASS: mentions add" || echo "FAIL: no add"
grep -i "subtract" "$TEST_DIR/output.log" && echo "PASS: mentions subtract" || echo "FAIL: no subtract"
```

---

## TC-AGENT-002: 子 Agent 并行任务

**优先级**: P1
**前置条件**: cody 已安装，LLM 可用
**涉及功能**: 多个子 Agent 并行

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/agent_002"
mkdir -p "$TEST_DIR/src" "$TEST_DIR/docs"
echo 'def hello(): pass' > "$TEST_DIR/src/app.py"
echo '# API Documentation' > "$TEST_DIR/docs/api.md"

cody run --workdir "$TEST_DIR" "使用两个子 Agent 并行完成：1) 分析 src/ 目录的代码 2) 分析 docs/ 目录的文档。最后汇总两个结果给我" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 尝试并行分析
- 输出提到 src 和 docs 的内容

### 验证方法

```bash
grep -i -E "app\.py|hello|src" "$TEST_DIR/output.log" && echo "PASS: analyzed src" || echo "FAIL: no src"
grep -i -E "api|docs|documentation" "$TEST_DIR/output.log" && echo "PASS: analyzed docs" || echo "FAIL: no docs"
```
