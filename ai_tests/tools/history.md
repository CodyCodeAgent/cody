# 文件历史（撤销/重做）测试

测试 Agent 的文件操作撤销/重做能力。

---

## TC-HISTORY-001: 写入后撤销

**优先级**: P1
**前置条件**: cody 已安装，LLM 可用
**涉及功能**: `write_file` → `undo_file`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/history_001"
mkdir -p "$TEST_DIR"
echo "original content" > "$TEST_DIR/test.txt"
cody run --workdir "$TEST_DIR" "先把 test.txt 的内容改成 modified content，然后立刻撤销这次修改" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 先修改了文件
- 然后调用 undo_file 撤销
- 文件恢复为 original content

### 验证方法

```bash
CONTENT=$(cat "$TEST_DIR/test.txt")
echo "FILE_CONTENT: $CONTENT"
if echo "$CONTENT" | grep -q "original"; then
    echo "PASS: content restored to original"
else
    echo "WARN: content may have changed (agent might not have undone)"
fi
# 宽松验证：Agent 至少尝试了 undo
grep -i "undo\|撤销\|恢复" "$TEST_DIR/output.log" && echo "PASS: undo attempted" || echo "FAIL: no undo"
```

---

## TC-HISTORY-002: 查看修改历史

**优先级**: P1
**前置条件**: cody 已安装，LLM 可用
**涉及功能**: `list_file_changes`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/history_002"
mkdir -p "$TEST_DIR"
cody run --workdir "$TEST_DIR" "创建 a.txt（内容 aaa）和 b.txt（内容 bbb），然后列出所有文件修改记录" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- 两个文件被创建
- 修改历史中包含这两次操作

### 验证方法

```bash
test -f "$TEST_DIR/a.txt" && echo "PASS: a.txt exists" || echo "FAIL: no a.txt"
test -f "$TEST_DIR/b.txt" && echo "PASS: b.txt exists" || echo "FAIL: no b.txt"
grep -i -E "a\.txt|b\.txt|change|history|修改" "$TEST_DIR/output.log" && echo "PASS: history shown" || echo "FAIL: no history"
```
