"""Stable extension registry for Runtime plugins and application embedding."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from importlib.metadata import entry_points
from typing import Any, Callable


class RuntimeExtensionKind(str, Enum):
    TOOL = "tool"
    SKILL = "skill"
    MODEL_PROVIDER = "model_provider"
    AGENT_BACKEND = "agent_backend"
    WORKFLOW_NODE = "workflow_node"
    EVALUATOR = "evaluator"
    STORE_BACKEND = "store_backend"
    AUTH_PROVIDER = "auth_provider"
    PRESENTATION_ADAPTER = "presentation_adapter"


@dataclass(frozen=True)
class RuntimeExtension:
    kind: RuntimeExtensionKind
    name: str
    factory: Callable[..., Any]
    version: str = "1"
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeExtensionRegistry:
    """Versioned registry with optional Python entry-point discovery."""

    ENTRY_POINT_GROUP = "cody.runtime.extensions"

    def __init__(self):
        self._extensions: dict[tuple[RuntimeExtensionKind, str], RuntimeExtension] = {}

    def register(self, extension: RuntimeExtension) -> RuntimeExtension:
        key = (extension.kind, extension.name)
        if key in self._extensions:
            raise ValueError(
                f"Duplicate Runtime extension: {extension.kind.value}/{extension.name}"
            )
        self._extensions[key] = extension
        return extension

    def get(self, kind: RuntimeExtensionKind | str, name: str) -> RuntimeExtension | None:
        return self._extensions.get((RuntimeExtensionKind(kind), name))

    def require(self, kind: RuntimeExtensionKind | str, name: str) -> RuntimeExtension:
        extension = self.get(kind, name)
        if extension is None:
            raise KeyError(f"Runtime extension not found: {RuntimeExtensionKind(kind).value}/{name}")
        return extension

    def create(self, kind: RuntimeExtensionKind | str, name: str, **kwargs: Any) -> Any:
        return self.require(kind, name).factory(**kwargs)

    def list(self, kind: RuntimeExtensionKind | str | None = None) -> list[RuntimeExtension]:
        selected = list(self._extensions.values())
        if kind is not None:
            selected = [item for item in selected if item.kind == RuntimeExtensionKind(kind)]
        return sorted(selected, key=lambda item: (item.kind.value, item.name))

    def discover(self, *, group: str = ENTRY_POINT_GROUP) -> list[RuntimeExtension]:
        """Load extensions declared through the standard package entry point."""

        discovered = []
        for point in entry_points().select(group=group):
            loaded = point.load()
            extension = loaded() if callable(loaded) and not isinstance(loaded, RuntimeExtension) else loaded
            if not isinstance(extension, RuntimeExtension):
                raise TypeError(f"Entry point {point.name} did not return RuntimeExtension")
            discovered.append(self.register(extension))
        return discovered

    def workflow_node_handlers(self) -> dict[str, Any]:
        return {
            extension.name: extension.factory()
            for extension in self.list(RuntimeExtensionKind.WORKFLOW_NODE)
        }
