# 13 · 自定义工具与中间件

<div class="tutorial-outcome"><strong>完成后：</strong>你会把一个业务动作注册为模型工具，并在所有工具调用前后统一执行策略与脱敏。</div>

## 1. 编写带类型的工具

```python
from pydantic_ai import RunContext

from cody.core.deps import CodyDeps


async def lookup_service_owner(
    ctx: RunContext[CodyDeps],
    service: str,
) -> str:
    """Return the owning team for one service name."""
    owners = {"payments": "fintech-platform", "search": "discovery"}
    return owners.get(service, "unknown")
```

工具必须是 async 函数，第一个参数是 `RunContext[CodyDeps]`，其余参数用类型注解描述 schema，docstring 决定模型何时选择它。

## 2. 通过 Builder 注册

```python
from cody.sdk import Cody

client = (
    Cody()
    .workdir("/tmp/cody-tutorial")
    .tool(lookup_service_owner)
    .build()
)

async with client:
    result = await client.run("payments 服务由哪个团队负责？")
    print(result.output)
```

## 3. 添加 before/after hook

```python
import re


async def enforce_policy(tool_name: str, args: dict) -> dict | None:
    if tool_name == "exec_command" and "rm -rf" in str(args.get("command", "")):
        return None
    return args


async def redact_output(tool_name: str, args: dict, result: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", result)


client = (
    Cody()
    .workdir("/tmp/cody-tutorial")
    .tool(lookup_service_owner)
    .before_tool(enforce_policy)
    .after_tool(redact_output)
    .build()
)
```

`before_tool` 返回修改后的参数继续，返回 `None` 拒绝；多个 hook 按注册顺序执行。`after_tool` 可以转换返回给模型的文本。

## 4. 接入 Runtime 治理

SDK hook 适合应用内逻辑，但生产级权限、审批、审计与幂等仍应通过 Runtime Tool Registry / Tool Policy 统一管理。不要让自定义工具直接绕过 Sandbox 和 Approval 执行危险副作用。

## 验证清单

- 正常参数可以执行，返回值可被模型理解。
- 危险参数被拒绝并留下结构化事件。
- secret 不出现在模型上下文、event、artifact 或 audit。
- 工具的外部副作用有幂等键和超时。
