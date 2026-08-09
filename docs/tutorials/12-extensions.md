# 12 · 扩展 Runtime

<div class="tutorial-outcome"><strong>完成后：</strong>你会注册一个版本化扩展，并知道哪些扩展需要稳定名称、恢复契约和可信宿主权限。</div>

## 可扩展类型

Runtime Registry 支持 Tool、Skill、Model provider、Agent backend、Workflow node、Evaluator、Store backend、Auth provider 与 Presentation adapter。

## 1. 注册一个 Evaluator

```python
from cody.core.runtime import (
    RuntimeExtension,
    RuntimeExtensionKind,
    RuntimeExtensionRegistry,
)


def create_policy_evaluator():
    async def evaluate(state, metric):
        violations = state.data.get("policy_violations", [])
        return {
            "score": 1.0 if not violations else 0.0,
            "violations": violations,
        }

    return evaluate


registry = RuntimeExtensionRegistry()
registry.register(
    RuntimeExtension(
        kind=RuntimeExtensionKind.EVALUATOR,
        name="company-policy",
        version="1",
        factory=create_policy_evaluator,
        metadata={"owner": "platform-team"},
    )
)
```

重复的 `kind/name` 会被拒绝，避免扩展静默覆盖。

## 2. 通过 Python entry point 分发

扩展包的 `pyproject.toml`：

```toml
[project.entry-points."cody.runtime.extensions"]
company_policy = "company_cody.extension:build_extension"
```

```python
registry = RuntimeExtensionRegistry()
loaded = registry.discover()
```

入口函数应返回一个 `RuntimeExtension`，并保持 `name` 与 `version` 的兼容策略。

## 3. 恢复契约

Workflow node、condition、Agent backend 和 remote transport 参与恢复时必须满足：

- 新进程可用相同稳定名称重新注册。
- 输入输出可持久化且可版本迁移。
- 外部副作用具备幂等语义。
- 错误是结构化且可审计的。
- 旧 Run 需要的扩展版本仍然可获得，或提供明确迁移。

## 4. Remote Sandbox transport

```python
from cody.core.sandbox import RemoteSandboxBackend, SandboxManager

manager = SandboxManager()
manager.register(RemoteSandboxBackend(transport, name="remote"))
```

`transport` 负责 create、exec、spawn、pause、resume、snapshot、restore、fork 和 terminate。Cody 只定义适配契约，不提供托管 endpoint。

## 5. 安全边界

Python 扩展运行在可信宿主进程，权限等同 Cody 服务本身。生产部署应：

- 固定包版本和供应链来源。
- 审查扩展读取的环境变量、文件和网络。
- 将高风险 Tool 接入统一 policy 与 Approval。
- 不把安装第三方扩展误认为 guest Sandbox 隔离。

完成本篇后，可回到[指南总览](../guides/index.md)查阅各公共类型的完整细节。
