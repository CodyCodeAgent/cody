"""Cody - AI coding companion"""

from ._version import __version__  # noqa: F401

# Lazy import mapping: name -> (module, attribute)
_LAZY_IMPORTS = {
    "AsyncCodyClient": (".sdk.client", "AsyncCodyClient"),
    "CodyClient": (".sdk.client", "CodyClient"),
    "Cody": (".sdk.client", "Cody"),
    "CodyError": (".sdk.errors", "CodyError"),
    "CodyNotFoundError": (".sdk.errors", "CodyNotFoundError"),
    "RunResult": (".sdk.types", "RunResult"),
    "SessionDetail": (".sdk.types", "SessionDetail"),
    "SessionInfo": (".sdk.types", "SessionInfo"),
    "StreamChunk": (".sdk.types", "StreamChunk"),
    "ToolResult": (".sdk.types", "ToolResult"),
    "Usage": (".sdk.types", "Usage"),
    "config": (".sdk.config", "config"),
}

__all__ = ["__version__"] + list(_LAZY_IMPORTS.keys())


def __getattr__(name):
    """Lazy imports — heavy SDK symbols are loaded on first access, not at import time."""
    if name in _LAZY_IMPORTS:
        import importlib
        module_path, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(module_path, __package__)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module 'cody' has no attribute {name!r}")
