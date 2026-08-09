# 06 · 组织多 Agent 团队

<div class="tutorial-outcome"><strong>完成后：</strong>你会定义 specialist role 和任务 DAG，让无依赖任务并发，并把每个 Agent 的结果分别保存。</div>

## 1. 定义角色和后端

```python
import asyncio

from cody.core.runtime import AgentRole, AgentTask, AsyncMultiAgentCoordinator

coordinator = AsyncMultiAgentCoordinator(max_concurrency=3)


async def specialist_backend(task, state):
    # 生产实现可在这里调用受 Runtime 管理的 Agent backend。
    await asyncio.sleep(0)
    return {"summary": f"{task.task_id} completed"}


coordinator.register_agent(
    AgentRole("analyst", capabilities=frozenset({"analysis", "review"})),
    specialist_backend,
)
coordinator.register_agent(
    AgentRole("engineer", capabilities=frozenset({"implementation", "test"})),
    specialist_backend,
)
```

## 2. 定义任务 DAG

```python
tasks = [
    AgentTask.create(
        "分析失败根因",
        task_id="diagnose",
        required_capabilities={"analysis"},
    ),
    AgentTask.create(
        "梳理现有测试覆盖",
        task_id="test_inventory",
        required_capabilities={"test"},
    ),
    AgentTask.create(
        "根据诊断实现修复",
        task_id="implement",
        required_capabilities={"implementation"},
        depends_on=("diagnose", "test_inventory"),
    ),
    AgentTask.create(
        "审查最终变更",
        task_id="review",
        required_capabilities={"review"},
        depends_on=("implement",),
    ),
]
```

`diagnose` 与 `test_inventory` 会并发；`implement` 等待两者；`review` 最后执行。

## 3. 作为 Runtime 节点执行

```python
from cody import CodyRuntime
from cody.core.runtime import RuntimeStoreBundle, Workflow, WorkflowNodeType

workflow = (
    Workflow("team-fix")
    .node(
        "team",
        WorkflowNodeType.AGENT_TEAM,
        metadata={"agent_tasks": [task.to_dict() for task in tasks]},
    )
    .compile()
)

runtime = CodyRuntime(
    runner=object(),
    stores=RuntimeStoreBundle.for_workdir("/tmp/cody-tutorial"),
    multi_agent_coordinator=coordinator,
    max_concurrency=3,
)

run = await runtime.start(workflow)
result = await run.result()
print(result.state.data["agent_outputs"])
await runtime.close()
```

每个成功任务写入 `agent_outputs[task_id]`，避免多个 specialist 隐式覆盖同名字段；配置 Artifact Store 后，每项输出还会形成独立 Artifact。

## 4. 失败与回退

```python
task = AgentTask.create(
    "修复实现",
    task_id="fix",
    required_capabilities={"implementation"},
    preferred_agent_id="primary-engineer",
    fallback_agent_ids=("backup-engineer",),
    metadata={
        "max_attempts": 2,
        "timeout_seconds": 300,
        "retry_backoff_seconds": 1,
    },
)
```

依赖失败的任务会标记为 `skipped`；无关分支仍可完成。不要用无限自动重试掩盖系统性故障。

## 验证清单

- 用 barrier 或时间戳证明独立任务真的并发。
- 检查任务状态包含 `completed`、`failed` 或 `skipped`，没有永久 `pending`。
- 检查 `agent_outputs` 以 task_id 隔离。
- 检查 fallback agent、超时、取消和最大尝试次数。
