# Skills 系统测试

测试 `cody skills` 子命令组和 Skills 加载/启用/禁用功能。

---

## TC-SKILL-001: 列出所有技能

**优先级**: P0
**前置条件**: cody 已安装
**涉及功能**: `cody skills list`

### 操作步骤

```bash
cody skills list 2>&1 | tee /tmp/cody_skills_list.log
```

### 预期结果

- 列出所有内置技能（python, git, github, docker, npm 等）
- 每个技能显示启用/禁用状态和来源

### 验证方法

```bash
grep -i "python" /tmp/cody_skills_list.log && echo "PASS: has python" || echo "FAIL: no python"
grep -i "docker" /tmp/cody_skills_list.log && echo "PASS: has docker" || echo "FAIL: no docker"
grep -i "testing" /tmp/cody_skills_list.log && echo "PASS: has testing" || echo "FAIL: no testing"
grep -i "builtin" /tmp/cody_skills_list.log && echo "PASS: shows source" || echo "FAIL: no source"
```

---

## TC-SKILL-002: 查看技能文档

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `cody skills show <name>`

### 操作步骤

```bash
cody skills show python 2>&1 | tee /tmp/cody_skill_python.log
```

### 预期结果

- 显示 python 技能的完整文档内容
- 包含使用说明

### 验证方法

```bash
grep -i -E "python|pytest|pip|venv" /tmp/cody_skill_python.log && echo "PASS: has python docs" || echo "FAIL: no docs"
```

---

## TC-SKILL-003: 禁用和启用技能

**优先级**: P1
**前置条件**: cody 已安装
**涉及功能**: `cody skills enable/disable`

### 操作步骤

1. 禁用一个技能：
```bash
cody skills disable docker 2>&1 | tee /tmp/cody_skill_disable.log
```

2. 验证禁用状态：
```bash
cody skills list 2>&1 | tee /tmp/cody_skills_after_disable.log
```

3. 重新启用：
```bash
cody skills enable docker 2>&1 | tee /tmp/cody_skill_enable.log
```

4. 验证启用状态：
```bash
cody skills list 2>&1 | tee /tmp/cody_skills_after_enable.log
```

### 预期结果

- 禁用后 docker 显示为 off
- 启用后 docker 显示为 on

### 验证方法

```bash
grep -i "disabled" /tmp/cody_skill_disable.log && echo "PASS: disable ok" || echo "FAIL: disable failed"
grep -i "enabled" /tmp/cody_skill_enable.log && echo "PASS: enable ok" || echo "FAIL: enable failed"
```

---

## TC-SKILL-004: 不存在的技能

**优先级**: P2
**前置条件**: cody 已安装
**涉及功能**: 错误处理

### 操作步骤

```bash
cody skills show nonexistent_skill_xyz 2>&1 | tee /tmp/cody_skill_notfound.log
```

### 预期结果

- 不会崩溃
- 输出提示技能不存在

### 验证方法

```bash
grep -i "not found" /tmp/cody_skill_notfound.log && echo "PASS: shows not found" || echo "FAIL: no error msg"
```

---

## TC-SKILL-005: Agent 使用技能

**优先级**: P0
**前置条件**: cody 已安装，LLM 可用
**涉及功能**: Agent 通过 `list_skills` / `read_skill` 工具使用技能

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/skill_005"
mkdir -p "$TEST_DIR"
cody run --workdir "$TEST_DIR" "列出你可用的所有技能，告诉我有哪些" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- Agent 调用了 list_skills 工具
- 输出中提到了多个技能名称

### 验证方法

```bash
grep -i -E "python|docker|github|testing|npm" "$TEST_DIR/output.log" && echo "PASS: mentions skills" || echo "FAIL: no skills mentioned"
```
