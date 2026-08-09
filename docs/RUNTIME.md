# Cody Canonical Runtime

`CodyRuntime` 是 Cody 的权威执行入口。它把一次任务建模为持久化 Run，由 Workflow
调度 Step，并将模型、工具、人工审批、Quality Gate 和多 Agent 执行统一投影为
`RunEvent`。CLI、TUI、Web 和兼容 SDK 都读取同一组状态与事件。

## 1. 最小示例

```python
import asyncio

from cody import CodyRuntime
from cody.core import Config
from cody.core.runtime import RuntimeStoreBundle


async def main() -> None:
    workdir = "/path/to/project"
    config = Config.load(workdir=workdir)
    stores = RuntimeStoreBundle.for_workdir(workdir)

    async with CodyRuntime.from_config(config, workdir, stores=stores) as runtime:
        run = await runtime.start("修复当前项目中失败的测试")

        async for event in run.events():
            print(event.event_type.value, event.payload)

        result = await run.result()
        print(result.output)
        print(result.artifact_ids)


asyncio.run(main())
```

`RuntimeStoreBundle.for_workdir()` 使用与 CLI/TUI/Web 相同的 durable SQLite stores。
若不传 `stores`，`CodyRuntime.from_config()` 默认使用进程内存，只适合测试和一次性运行。

`RuntimeRun` 是当前进程中的活动句柄：

- `run_id`：跨所有 store 和产品表面的稳定标识。
- `events(from_index=0)`：按持久化顺序读取 canonical events。
- `result()`：等待结构化 `RuntimeRunResult`。
- `cancel()`：传播到模型执行和 workflow 安全边界。
- `pause(before_node_id=None)`：请求在安全节点边界持久化暂停。
- `record`、`done`、`sandbox`：当前记录、终态和 Run sandbox。

## 2. Run 生命周期

```mermaid
stateDiagram-v2
    [*] --> created
    created --> running
    running --> waiting: approval / human input
    running --> paused: pause request
    running --> completed
    running --> failed
    running --> cancelled
    waiting --> running: approve + resume
    paused --> running: resume
    failed --> running: retry / recover
    cancelled --> running: retry
    completed --> [*]
```

Runtime 持久化以下关联记录：

| 记录 | 作用 |
|------|------|
| Run/Step | 生命周期、workflow、输入输出、父子关系和状态 |
| RunEvent | 实时 timeline 的唯一权威事件源 |
| Checkpoint | 已提交的执行位置、state 和 sandbox snapshot 引用 |
| Artifact | 补丁、日志、上下文、审查结果、工具收据和 snapshot |
| Approval | 可跨进程批准或拒绝的人工决策 |
| Audit | actor、动作、目标和脱敏参数 |
| Control | 跨进程 pause/cancel 请求 |

## 3. Workflow

```python
from cody.core.runtime import Workflow, WorkflowEdgeType, WorkflowNodeType

workflow = (
    Workflow("verified-change")
    .node("plan", WorkflowNodeType.AGENT)
    .node("tests", WorkflowNodeType.TOOL, tool_name="run_tests")
    .node("review", WorkflowNodeType.QUALITY_GATE)
    .node("done", WorkflowNodeType.FUNCTION)
    .edge("plan", "tests")
    .edge("tests", "review")
    .edge("review", "done")
)

run = await runtime.start(workflow, {"task": "修复失败测试"})
```

节点类型包括 Agent、Tool、Function、Checkpoint、Human Approval、Agent Team、Quality
Gate 和 Nested Workflow。条件路由由 Conditional Edge 表达；Edge 支持 sequential、parallel、join、conditional 和
fallback。编译阶段会拒绝悬空边、非法 join、无入口图和不允许的环。

节点 `metadata` 常用字段：

- `timeout_seconds`：节点超时。
- `max_retries`、`retry_backoff_seconds`：有限重试。
- `allow_revisit`：明确允许 repair loop 回访节点。
- `merge_policy`：并行输出冲突采用 `error`、`last_write_wins` 或 `namespace`。

Runtime 的 `max_concurrency` 控制 ready 节点的并发数；`start(..., max_steps=...)`
是全局循环保护。并行结果按 node id 确定性合并。

## 4. 审批、恢复、重试与 Fork

审批节点和需要 `confirm` 的模型工具会创建 durable Approval。Run 进入 `waiting` 后
释放 worker；批准可以来自另一个 CLI/Web 进程：

```python
runtime.approve(approval_id, {"approved": True})
resumed = await runtime.resume(run_id)
result = await resumed.result()
```

服务崩溃或进程被终止后：

```python
recovered = await runtime.recover(run_id)
```

失败/取消运行和历史 checkpoint：

```python
retried = await runtime.retry(run_id, checkpoint_id=checkpoint_id)
forked = await runtime.fork(
    checkpoint_id,
    new_run_id="run_alternative",
    metadata={"reason": "alternate implementation"},
)
```

恢复要求：

1. Run 使用 durable store，而不是 `in_memory()`。
2. workflow 定义可从 RunRecord 反序列化。
3. 自定义 node/condition handler 在新 Runtime 中以同名重新注册。
4. 外部副作用工具使用 Runtime Tool Registry 的幂等收据；必要时声明
   `metadata={"idempotency_arg": "request_id"}`。
5. Sandbox snapshot 的引用在进程重启后仍然可访问。

## 5. 多 Agent 团队

`AsyncMultiAgentCoordinator` 接受 specialist role 和 task DAG。无依赖任务并发，后续
任务等待依赖完成；失败可以配置 preferred/fallback agent、timeout 和 max attempts。

```python
from cody.core.runtime import AsyncMultiAgentCoordinator

coordinator = AsyncMultiAgentCoordinator(max_concurrency=4)
coordinator.register_agent(code_role, code_backend)
coordinator.register_agent(test_role, test_backend)

runtime = CodyRuntime.from_config(
    config,
    workdir,
    multi_agent_coordinator=coordinator,
    max_concurrency=4,
)
```

成功任务分别保存 Artifact，输出放入 `agent_outputs[task_id]`，避免多个 specialist
隐式覆盖同名字段。

## 6. Quality Gate 与修复循环

Quality Gate 并发执行 evaluator。每次 decision 都写入 event、checkpoint 和 REVIEW
Artifact。失败时可通过 fallback edge 进入 repair，再用 `allow_revisit` 返回 gate。

```python
from cody.core.runtime import standard_quality_evaluators

runtime = CodyRuntime.from_config(
    config,
    workdir,
    quality_evaluators=standard_quality_evaluators(workdir),
)
```

标准 evaluator 使用 argv 执行测试/lint，不通过 shell 拼接命令，并返回结构化
stdout、stderr、return code 和 timeout。生产工作流必须同时限制 `max_repairs`、节点
重试次数、Run step/token/cost/time 预算。

## 7. 治理上下文与预算

```python
from cody.core.runtime import RuntimeBudget, RuntimeRunContext

run = await runtime.start(
    workflow,
    {"task": "审查并修复"},
    context=RuntimeRunContext(
        actor_id="user-42",
        service_account_id="ci-reviewer",
        project_id="payments",
        permissions={"tools": ["read_file", "grep", "edit_file"]},
    ),
    budget=RuntimeBudget(
        max_steps=80,
        max_duration_seconds=900,
        max_tokens=500_000,
        max_cost_usd=5.0,
    ),
)
```

Runtime policy 和 AgentRunner 工具策略共享治理路径。事件、审计和 Artifact metadata
在持久化前递归脱敏；不要依赖脱敏替代 secret manager，也不要把密钥放入 prompt、
workflow metadata 或工具参数。

## 8. Store 与部署模式

### 本地/单机 SQLite

产品表面默认按规范化 workdir 使用稳定目录：

```text
~/.cody/runtime/<sha256(workdir)[:20]>/
```

可用 `CODY_RUNTIME_HOME` 修改根目录。SDK 显式配置：

```python
from cody.core.runtime import RuntimeStoreBundle

stores = RuntimeStoreBundle.for_workdir(workdir)
runtime = CodyRuntime.from_config(config, workdir, stores=stores)
```

### PostgreSQL 多进程部署

安装生产依赖：

```bash
pip install 'cody-ai[production]'
```

```python
stores = RuntimeStoreBundle.postgres(
    "postgresql://cody:password@db.example/cody",
    schema="agent_runtime",
)
runtime = CodyRuntime.from_config(config, workdir, stores=stores)
```

PostgreSQL 适配器在一个带索引的 JSONB catalog 中保存 Run、Step、Event、Checkpoint、
Approval、Artifact metadata、Audit 和 Control。迁移、连接池、TLS、备份、保留策略和
高可用由部署方负责。

### 大型 Artifact 对象存储

```python
from cody.core.runtime import S3ObjectStorage

objects = S3ObjectStorage(
    "cody-artifacts",
    prefix="production",
    put_options={"ServerSideEncryption": "AES256"},
    endpoint_url="https://s3.example.com",
    region_name="us-east-1",
)
stores = RuntimeStoreBundle.postgres(dsn, object_storage=objects)
```

也可使用 `FileSystemObjectStorage`。数据库只保存 metadata/object key，读取 Artifact
时自动回填 payload。生产环境应配置服务账号、服务端加密、生命周期、版本控制和
最小权限 bucket policy。

## 9. Sandbox

Runtime 为每个 Run 创建 `SandboxHandle`。Command、Quality Gate、stdio MCP、LSP 和
子 Agent 命令共用同一执行边界；等待审批时 snapshot，恢复时 restore。

启用方式、后端差异和网络策略见 [Sandbox 指南](SANDBOX.md)。Python hook、自定义
node handler、model provider 和 extension 在可信宿主进程运行，不属于 guest sandbox。

## 10. 可观测与产品表面

```bash
cody runs list --workdir /path/to/project
cody runs show <run_id>
cody runs watch <run_id>
cody runs metrics <run_id>
cody timeline show <run_id>
cody timeline checkpoints <run_id>
cody artifacts list --run-id <run_id>
cody approvals list --status pending
```

Web `/runtime/*`、CLI 和 React Runtime console 读取相同的 stores。Timeline、metrics、
checkpoint、artifact 和 audit 都通过 `run_id`/`step_id` 关联。

## 11. 扩展

`RuntimeExtensionRegistry` 支持版本化扩展和 Python entry-point discovery：Tool、Skill、
Model provider、Agent backend、Workflow node、Evaluator、Store、Auth 和 Presentation
adapter。扩展应只依赖公共类型，不修改 Runtime 内核；恢复所需的 handler 必须使用
稳定名称和兼容版本。

## 12. 当前边界 {#12-当前边界}

- SQLite 适合单机；多进程生产部署使用 PostgreSQL 或自定义 Store。
- S3/PostgreSQL、Docker/Podman 和 Bubblewrap 需要对应外部服务或系统依赖，安装包
  不会自动提供它们。
- Remote Sandbox 只提供 provider-neutral transport/handle adapter，不包含托管远程
  沙箱服务；部署方必须实现并注册 transport。
- `local-policy` 只做路径、命令和环境策略检查，不是 OS 安全边界。
- 视觉输入是否可用由所配置模型端点决定；文本模型不会因为 Cody 支持图片 payload
  就自动获得视觉能力。
- 自定义 Python 扩展是可信代码，不能用 guest Sandbox 隔离。

**最后更新：2026-08-08**
