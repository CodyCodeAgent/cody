# 04 · 启动持久化 Run

<div class="tutorial-outcome"><strong>完成后：</strong>你会启动一个 durable Run，读取 canonical events，并在进程结束后仍能通过 run_id 查询它。</div>

## SDK 调用与 Runtime Run 的区别

`AsyncCodyClient` 是兼容且易用的产品 SDK；`CodyRuntime` 是权威执行入口。需要审批、恢复、Workflow、Artifact、跨进程控制或统一 timeline 时，应显式使用 Runtime。

## 1. 使用工作区持久化 Store

```python
import asyncio

from cody import CodyRuntime
from cody.core import Config
from cody.core.runtime import RuntimeStoreBundle


async def main() -> None:
    workdir = "/tmp/cody-tutorial"
    config = Config.load(workdir=workdir)
    stores = RuntimeStoreBundle.for_workdir(workdir)

    async with CodyRuntime.from_config(config, workdir, stores=stores) as runtime:
        run = await runtime.start("运行测试，修复失败项，并总结变更")
        print("run_id:", run.run_id)

        async for event in run.events():
            print(event.event_type.value, event.step_id, event.payload)

        result = await run.result()
        print("status:", result.run.status.value)
        print("artifacts:", result.artifact_ids)
        print(result.output)


asyncio.run(main())
```

默认数据目录是 `~/.cody/runtime/<workdir-hash>/`，可用 `CODY_RUNTIME_HOME` 修改根目录。

## 2. 在另一个终端观察

脚本运行期间或结束后执行：

```bash
cody runs list --workdir /tmp/cody-tutorial
cody runs show <run_id> --workdir /tmp/cody-tutorial
cody runs watch <run_id> --workdir /tmp/cody-tutorial
cody runs metrics <run_id> --workdir /tmp/cody-tutorial
cody timeline show <run_id> --workdir /tmp/cody-tutorial
cody artifacts list --run-id <run_id> --workdir /tmp/cody-tutorial
```

以实际 `cody <group> <command> --help` 为参数权威来源。

## 3. 不要在需要恢复时使用内存 Store

```python
stores = RuntimeStoreBundle.in_memory()
```

这只适合单元测试和一次性进程。进程结束后 Run、Approval、Checkpoint 和 Artifact 都不可恢复。

## 4. 关联关系

一次 Run 的所有证据都通过稳定标识关联：

```text
run_id
├── step_id
├── event_id
├── checkpoint_id
├── approval_id
├── artifact_id
└── audit record
```

这也是 CLI、TUI、Web 和 SDK 能看到同一状态的基础。
