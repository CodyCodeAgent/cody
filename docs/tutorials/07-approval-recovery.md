# 07 · 审批、暂停与恢复

<div class="tutorial-outcome"><strong>完成后：</strong>你会让 Run 在等待审批时释放 worker，并从另一个进程批准、恢复或 fork。</div>

## 1. 在 Workflow 中加入审批

```python
from cody.core.runtime import Workflow, WorkflowNodeType

workflow = (
    Workflow("reviewed-change")
    .node("implement", WorkflowNodeType.AGENT, agent_name="code")
    .node(
        "approval",
        WorkflowNodeType.HUMAN_APPROVAL,
        metadata={"request": {"action": "approve_final_diff"}},
    )
    .node("deliver", WorkflowNodeType.FUNCTION)
    .edge("implement", "approval")
    .edge("approval", "deliver")
)
```

审批节点或权限为 `confirm` 的工具会创建 durable Approval。Run 状态变成 `waiting`，checkpoint 和 sandbox snapshot 被保存，当前 worker 可以退出。

## 2. 从另一个终端处理审批

```bash
cody approvals list --status pending --workdir /tmp/cody-tutorial
cody approvals approve <approval_id> --workdir /tmp/cody-tutorial
cody runs resume <run_id> --workdir /tmp/cody-tutorial
```

拒绝操作：

```bash
cody approvals reject <approval_id> --workdir /tmp/cody-tutorial
```

CLI 与 Web 使用同一 Approval Store，因此从一个界面发起的 Run 可以在另一个界面批准。

## 3. 暂停与取消

```bash
cody runs pause <run_id> --workdir /tmp/cody-tutorial
cody runs cancel <run_id> --workdir /tmp/cody-tutorial
```

暂停在下一个安全节点边界生效；取消会继续向当前模型、工具与子任务传播。跨进程控制通过 durable Control record 实现，而不是依赖内存变量。

## 4. 进程终止后恢复

如果服务在 Run 仍标记为 `running` 时被强制终止：

```bash
cody runs recover <run_id> --workdir /tmp/cody-tutorial
```

如果 Run 已处于 `waiting` 或 `paused`：

```bash
cody runs resume <run_id> --workdir /tmp/cody-tutorial
```

失败或取消的 Run 可以重试：

```bash
cody runs retry <run_id> --workdir /tmp/cody-tutorial
```

从历史 checkpoint 产生一条独立分支：

```bash
cody timeline checkpoints <run_id> --workdir /tmp/cody-tutorial
cody runs fork <checkpoint_id> --workdir /tmp/cody-tutorial
```

## 恢复成立的条件

1. 使用 SQLite、PostgreSQL 或自定义 durable Store，不能使用内存 Store。
2. Workflow 可以从 RunRecord 反序列化。
3. 自定义 handler 在新进程以相同稳定名称注册。
4. 外部副作用工具有幂等键或 Runtime 收据。
5. Sandbox snapshot reference 在新进程仍可访问。

!!! danger "恢复不等于重新运行"
    支付、发布、删除等副作用如果没有幂等语义，恢复时可能重复执行。此类工具应强制审批，并通过业务幂等键或 Runtime receipt 去重。
