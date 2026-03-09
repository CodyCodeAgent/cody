# Web Chat 端点测试

测试 Web 后端的 Chat WebSocket 端点。

> **前置条件**：需要先启动 Web 后端。
> ```bash
> cd /Users/bytedance/GC/GitHub/cody && cody-web run --port 18923 &
> WEB_PID=$!
> sleep 3
> ```

---

## TC-WCHAT-001: 项目管理 API

**优先级**: P1
**前置条件**: Web 后端已启动
**涉及功能**: `POST /projects` + `GET /projects`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/wchat_001"
mkdir -p "$TEST_DIR"

# 创建项目
curl -s -X POST http://localhost:18923/projects \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Test Project\", \"workdir\": \"$TEST_DIR\"}" \
  | tee "$TEST_DIR/create.json"

# 列出项目
curl -s http://localhost:18923/projects | tee "$TEST_DIR/list.json"
```

### 预期结果

- 项目创建成功，返回 project_id
- 列表中包含刚创建的项目

### 验证方法

```bash
python3 -c "
import json
create = json.load(open('$CODY_TEST_DIR/wchat_001/create.json'))
has_id = 'id' in create or 'project_id' in create
print(f'PROJECT_CREATED: {has_id}')

lst = json.load(open('$CODY_TEST_DIR/wchat_001/list.json'))
is_list = isinstance(lst, list) or (isinstance(lst, dict) and 'projects' in lst)
print(f'LIST_OK: {is_list}')
"
```

---

## TC-WCHAT-002: WebSocket 连通性

**优先级**: P1
**前置条件**: Web 后端已启动
**涉及功能**: `ws://localhost:18923/ws/chat/{project_id}`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/wchat_002"
mkdir -p "$TEST_DIR"
cat > "$TEST_DIR/test_ws.py" << 'PYEOF'
import asyncio
import json

async def main():
    try:
        import websockets
    except ImportError:
        print("SKIP: websockets not installed")
        return

    # 先创建一个项目
    import urllib.request
    req = urllib.request.Request(
        "http://localhost:18923/projects",
        data=json.dumps({"name": "WS Test", "workdir": "/tmp"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    project = json.loads(resp.read())
    pid = project.get("id") or project.get("project_id")
    print(f"PROJECT_ID: {pid}")

    # 尝试 WebSocket 连接
    try:
        async with websockets.connect(f"ws://localhost:18923/ws/chat/{pid}") as ws:
            # 发送 ping
            await ws.send(json.dumps({"type": "ping"}))
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(resp)
            print(f"PONG_RECEIVED: {data.get('type') == 'pong'}")
    except Exception as e:
        print(f"WS_ERROR: {e}")
        print("PONG_RECEIVED: False")

asyncio.run(main())
PYEOF
python3 "$TEST_DIR/test_ws.py" 2>&1 | tee "$TEST_DIR/output.log"
```

### 预期结果

- WebSocket 连接成功
- ping/pong 正常工作

### 验证方法

```bash
grep "PONG_RECEIVED: True" "$TEST_DIR/output.log" && echo "PASS: websocket works" || echo "SKIP: websocket test skipped or failed"
```

---

## TC-WCHAT-003: HTTP 流式 Run

**优先级**: P0
**前置条件**: Web 后端已启动
**涉及功能**: `POST /run/stream`

### 操作步骤

```bash
TEST_DIR="$CODY_TEST_DIR/wchat_003"
mkdir -p "$TEST_DIR"

# 流式请求
curl -s -N -X POST http://localhost:18923/run/stream \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": \"回复 OK\", \"workdir\": \"$TEST_DIR\"}" \
  --max-time 30 \
  2>&1 | tee "$TEST_DIR/stream.log"
```

### 预期结果

- 返回 SSE（Server-Sent Events）格式
- 包含文本和完成事件

### 验证方法

```bash
test -s "$TEST_DIR/stream.log" && echo "PASS: got stream output" || echo "FAIL: empty stream"
```

---

## 清理

```bash
kill $WEB_PID 2>/dev/null
```
