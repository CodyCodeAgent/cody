from cody.core.runtime import (
    CodyRuntime,
    RuntimeExtension,
    RuntimeExtensionKind,
    RuntimeExtensionRegistry,
    Workflow,
    WorkflowNodeType,
)


def test_extension_registry_creates_typed_extension():
    registry = RuntimeExtensionRegistry()
    registry.register(RuntimeExtension(
        RuntimeExtensionKind.MODEL_PROVIDER,
        "private-model",
        lambda endpoint: {"endpoint": endpoint},
    ))

    assert registry.create(
        RuntimeExtensionKind.MODEL_PROVIDER,
        "private-model",
        endpoint="https://model.internal",
    ) == {"endpoint": "https://model.internal"}


async def test_custom_workflow_node_extension_runs_without_kernel_change():
    async def handler(state, node):
        return {"output": f"extended:{state.data['task']}"}

    registry = RuntimeExtensionRegistry()
    registry.register(RuntimeExtension(
        RuntimeExtensionKind.WORKFLOW_NODE,
        "function",
        lambda: handler,
    ))
    workflow = Workflow("extension").node(
        "custom-node", WorkflowNodeType.FUNCTION
    ).compile()
    runtime = CodyRuntime(object(), extensions=registry, poll_interval=0)

    result = await (await runtime.start(workflow, {"task": "ok"})).result()

    assert result.output == "extended:ok"
