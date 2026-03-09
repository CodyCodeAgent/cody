# Web API 端点测试

测试 Web 后端的 HTTP API 端点。

> **前置条件**：需要先启动 Web 后端。测试前执行：
> ```bash
> cd /Users/bytedance/GC/GitHub/cody && cody-web run --port 18923 &
> WEB_PID=$!
> sleep 3
> ```
> 测试完毕后执行 `kill $WEB_PID`

---

## TC-WEB-001: 健康检查

**优先级**: P0
**前置条件**: Web 后端已启动
**涉及功能**: `GET /health`

### 操作步骤

```bash
curl -s http://localhost:18923/health | tee /tmp/cody_health.json
```

### 预期结果

- 返回 200
- JSON 包含 `status` 字段

### 验证方法

```bash
python3 -c "
import json
data = json.load(open('/tmp/cody_health.json'))
print(f'HAS_STATUS: {\"status\" in data}')
print(f'STATUS_OK: {data.get(\"status\") == \"ok\"}')
"
```

---

## TC-WEB-002: 执行任务

**优先级**: P0
**前置条件**: Web 后端已启动
**涉及功能**: `POST /run`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/web_002"
mkdir -p "$TEST_DIR"
curl -s -X POST http://localhost:18923/run \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": \"回复 OK\", \"workdir\": \"$TEST_DIR\"}" \
  | tee "$TEST_DIR/run_result.json"
```

### 预期结果

- 返回 200
- JSON 包含 `output` 字段
- output 不为空

### 验证方法

```bash
python3 -c "
import json
data = json.load(open('$CODY_TEST_DIR/web_002/run_result.json'))
print(f'HAS_OUTPUT: {\"output\" in data}')
print(f'OUTPUT_OK: {bool(data.get(\"output\", \"\"))}')
"
```

---

## TC-WEB-003: 会话列表 API

**优先级**: P1
**前置条件**: Web 后端已启动
**涉及功能**: `GET /sessions`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/web_003"
mkdir -p "$TEST_DIR"
curl -s http://localhost:18923/sessions | tee "$TEST_DIR/sessions.json"
```

### 预期结果

- 返回 200
- 返回 JSON，包含 `sessions` 字段（数组）

### 验证方法

```bash
python3 -c "
import json
data = json.load(open('$CODY_TEST_DIR/web_003/sessions.json'))
sessions = data.get('sessions', []) if isinstance(data, dict) else data
is_list = isinstance(sessions, list)
print(f'IS_LIST: {is_list}')
print(f'COUNT: {len(sessions)}')
"
```

---

## TC-WEB-004: Skills 列表 API

**优先级**: P1
**前置条件**: Web 后端已启动
**涉及功能**: `GET /skills`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/web_004"
mkdir -p "$TEST_DIR"
curl -s http://localhost:18923/skills | tee "$TEST_DIR/skills.json"
```

### 预期结果

- 返回 200
- 返回 JSON，包含 `skills` 字段（技能列表数组），含内置技能（如 git, python 等）

### 验证方法

```bash
python3 -c "
import json
data = json.load(open('$CODY_TEST_DIR/web_004/skills.json'))
skills = data.get('skills', []) if isinstance(data, dict) else data
is_list = isinstance(skills, list)
print(f'IS_LIST: {is_list}')
names = [s.get('name', '') for s in skills] if is_list else []
print(f'HAS_GIT: {\"git\" in names}')
print(f'HAS_PYTHON: {\"python\" in names}')
print(f'SKILL_COUNT: {len(skills)}')
"
```

---

## TC-WEB-005: 配置 API

**优先级**: P1
**前置条件**: Web 后端已启动
**涉及功能**: `GET /config`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/web_005"
mkdir -p "$TEST_DIR"
curl -s http://localhost:18923/config | tee "$TEST_DIR/config.json"
```

### 预期结果

- 返回 200
- JSON 包含 `model` 字段

### 验证方法

```bash
python3 -c "
import json
data = json.load(open('$CODY_TEST_DIR/web_005/config.json'))
print(f'HAS_MODEL: {\"model\" in data}')
print(f'MODEL: {data.get(\"model\", \"N/A\")}')
"
```

---

## TC-WEB-006: 目录浏览 API

**优先级**: P2
**前置条件**: Web 后端已启动
**涉及功能**: `GET /api/directories`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/web_006"
mkdir -p "$TEST_DIR"
# 在测试目录创建几个文件
echo "test" > "$TEST_DIR/a.txt"
echo "test" > "$TEST_DIR/b.py"
mkdir -p "$TEST_DIR/subdir"

curl -s "http://localhost:18923/api/directories?path=$TEST_DIR" | tee "$TEST_DIR/dir.json"
```

### 预期结果

- 返回目录内容列表
- 包含创建的文件和子目录

### 验证方法

```bash
python3 -c "
import json
data = json.load(open('$CODY_TEST_DIR/web_006/dir.json'))
print(f'IS_LIST: {isinstance(data, list)}')
if isinstance(data, list):
    names = [item.get('name', '') for item in data]
    print(f'HAS_FILES: {\"a.txt\" in names or len(names) > 0}')
"
```

---

## 清理

测试完毕后停止 Web 后端：

```bash
kill $WEB_PID 2>/dev/null
echo "Web backend stopped"
```
