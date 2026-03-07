"""Cody Core - AI Agent Framework"""

# Mapping of public names to (module_path, name_in_module)
_LAZY_IMPORTS = {
    # config
    "Config": (".config", "Config"),
    # runner
    "AgentRunner": (".runner", "AgentRunner"),
    "CodyResult": (".runner", "CodyResult"),
    "ToolTrace": (".runner", "ToolTrace"),
    "StreamEvent": (".runner", "StreamEvent"),
    "CompactEvent": (".runner", "CompactEvent"),
    "ThinkingEvent": (".runner", "ThinkingEvent"),
    "TextDeltaEvent": (".runner", "TextDeltaEvent"),
    "ToolCallEvent": (".runner", "ToolCallEvent"),
    "ToolResultEvent": (".runner", "ToolResultEvent"),
    "DoneEvent": (".runner", "DoneEvent"),
    # session
    "SessionStore": (".session", "SessionStore"),
    # skill_manager
    "SkillManager": (".skill_manager", "SkillManager"),
    # errors
    "CodyAPIError": (".errors", "CodyAPIError"),
    "ErrorCode": (".errors", "ErrorCode"),
    "ErrorDetail": (".errors", "ErrorDetail"),
    # mcp / lsp
    "MCPClient": (".mcp_client", "MCPClient"),
    "LSPClient": (".lsp_client", "LSPClient"),
    # sub_agent
    "SubAgentManager": (".sub_agent", "SubAgentManager"),
    # context
    "CompactResult": (".context", "CompactResult"),
    "FileChunk": (".context", "FileChunk"),
    "chunk_file": (".context", "chunk_file"),
    "compact_messages": (".context", "compact_messages"),
    "select_relevant_context": (".context", "select_relevant_context"),
    # audit
    "AuditLogger": (".audit", "AuditLogger"),
    "AuditEntry": (".audit", "AuditEntry"),
    "AuditEvent": (".audit", "AuditEvent"),
    # auth
    "AuthManager": (".auth", "AuthManager"),
    "AuthToken": (".auth", "AuthToken"),
    "AuthError": (".auth", "AuthError"),
    # permissions
    "PermissionManager": (".permissions", "PermissionManager"),
    "PermissionLevel": (".permissions", "PermissionLevel"),
    "PermissionDeniedError": (".permissions", "PermissionDeniedError"),
    # file_history
    "FileHistory": (".file_history", "FileHistory"),
    "FileChange": (".file_history", "FileChange"),
    # rate_limiter
    "RateLimiter": (".rate_limiter", "RateLimiter"),
    "RateLimitResult": (".rate_limiter", "RateLimitResult"),
    # deps
    "CodyDeps": (".deps", "CodyDeps"),
    # log
    "setup_logging": (".log", "setup_logging"),
    # model_resolver
    "resolve_model": (".model_resolver", "resolve_model"),
    # project_instructions
    "CODY_MD_FILENAME": (".project_instructions", "CODY_MD_FILENAME"),
    "CODY_MD_TEMPLATE": (".project_instructions", "CODY_MD_TEMPLATE"),
    "generate_project_instructions": (".project_instructions", "generate_project_instructions"),
    "load_project_instructions": (".project_instructions", "load_project_instructions"),
    # prompt
    "ImageData": (".prompt", "ImageData"),
    "MultimodalPrompt": (".prompt", "MultimodalPrompt"),
    "Prompt": (".prompt", "Prompt"),
    "prompt_images": (".prompt", "prompt_images"),
    "prompt_text": (".prompt", "prompt_text"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib
        mod = importlib.import_module(module_path, __package__)
        val = getattr(mod, attr)
        # Cache on the module to avoid repeated __getattr__ calls
        globals()[name] = val
        return val
    raise AttributeError(f"module 'cody.core' has no attribute {name!r}")
