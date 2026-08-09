# 15 · 记忆、事件与指标

<div class="tutorial-outcome"><strong>完成后：</strong>你会保存项目级知识，监听 SDK 生命周期事件，并输出基本调用指标。</div>

## 1. 保存项目记忆

```python
await client.add_memory(
    category="conventions",
    content="本项目使用 Ruff，行宽 100；公共函数必须有类型注解。",
    confidence=0.95,
    tags=["python", "style"],
)

await client.add_memory(
    category="decisions",
    content="Runtime catalog 在生产环境使用 PostgreSQL。",
    source_task_id="architecture-review",
)
```

类别包括 `conventions`、`patterns`、`issues` 和 `decisions`。低置信度、过期或未经验证的信息不应自动写入长期记忆。

## 2. 查询与清除

```python
memory = await client.get_memory()
for category, entries in memory.items():
    for entry in entries:
        print(category, entry["content"])

# 确认确实要删除后再执行
await client.clear_memory()
```

项目记忆按规范化 workdir 隔离，并在后续 Agent 系统 Prompt 中注入。它不是向量数据库，也不替代版本化架构文档。

## 3. 监听事件

```python
from cody.sdk import Cody, EventType


def on_tool_start(event) -> None:
    print("tool:", event.data)


client = (
    Cody()
    .workdir("/tmp/cody-tutorial")
    .enable_events()
    .on(EventType.TOOL_CALL_STARTED, on_tool_start)
    .enable_metrics()
    .build()
)
```

事件 hook 适合应用内通知；跨进程 Timeline 应读取 canonical Runtime Event Store。

## 4. 输出指标

```python
async with client:
    await client.run("检查项目结构")
    metrics = client.get_metrics()
    print(metrics)
```

SDK metrics 关注当前客户端调用；Runtime metrics 还会关联 workflow node、retry、gate、artifact 与 duration：

```bash
cody runs metrics <run_id> --workdir /tmp/cody-tutorial
```

## 观测边界

- 不在日志或 event 中记录 API Key、凭据、原始 Authorization header。
- 用 run_id/step_id 关联日志、指标和 Artifact。
- 将模型的“我已完成”视为文本，不视为测试证据。
- 生产告警应关注失败率、等待时长、重试风暴、预算耗尽和 Sandbox fallback。
