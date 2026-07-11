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
    "PruneEvent": (".runner", "PruneEvent"),
    "CompactEvent": (".runner", "CompactEvent"),
    "ThinkingEvent": (".runner", "ThinkingEvent"),
    "TextDeltaEvent": (".runner", "TextDeltaEvent"),
    "ToolCallEvent": (".runner", "ToolCallEvent"),
    "ToolResultEvent": (".runner", "ToolResultEvent"),
    "DoneEvent": (".runner", "DoneEvent"),
    "CancelledEvent": (".runner", "CancelledEvent"),
    "SessionStartEvent": (".runner", "SessionStartEvent"),
    "CircuitBreakerEvent": (".runner", "CircuitBreakerEvent"),
    "InteractionRequestEvent": (".runner", "InteractionRequestEvent"),
    "UserInputReceivedEvent": (".runner", "UserInputReceivedEvent"),
    "TaskMetadata": (".runner", "TaskMetadata"),
    # interaction
    "InteractionRequest": (".interaction", "InteractionRequest"),
    "InteractionResponse": (".interaction", "InteractionResponse"),
    "InteractionTimeoutError": (".errors", "InteractionTimeoutError"),
    # memory
    "ProjectMemoryStore": (".memory", "ProjectMemoryStore"),
    "MemoryEntry": (".memory", "MemoryEntry"),
    # circuit_breaker error
    "CircuitBreakerError": (".errors", "CircuitBreakerError"),
    # config
    "CircuitBreakerConfig": (".config", "CircuitBreakerConfig"),
    "TruncationConfig": (".config", "TruncationConfig"),
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
    "PruneResult": (".context", "PruneResult"),
    "prune_tool_outputs": (".context", "prune_tool_outputs"),
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
    # retry
    "RetryConfig": (".config", "RetryConfig"),
    # user_input
    "UserInputQueue": (".user_input", "UserInputQueue"),
    # deps
    "CodyDeps": (".deps", "CodyDeps"),
    # runtime
    "AgentRole": (".runtime", "AgentRole"),
    "AgentTask": (".runtime", "AgentTask"),
    "AgentTaskRecord": (".runtime", "AgentTaskRecord"),
    "AgentTaskStatus": (".runtime", "AgentTaskStatus"),
    "ApprovalRequestRecord": (".runtime", "ApprovalRequestRecord"),
    "ApprovalStatus": (".runtime", "ApprovalStatus"),
    "ArtifactRecord": (".runtime", "ArtifactRecord"),
    "ArtifactType": (".runtime", "ArtifactType"),
    "agent_node_handler": (".runtime", "agent_node_handler"),
    "agent_runner_backend": (".runtime", "agent_runner_backend"),
    "agent_runner_streaming_backend": (".runtime", "agent_runner_streaming_backend"),
    "AsyncWorkflowExecutionError": (".runtime", "AsyncWorkflowExecutionError"),
    "AsyncWorkflowExecutor": (".runtime", "AsyncWorkflowExecutor"),
    "RunEvent": (".runtime", "RunEvent"),
    "RuntimeAPIResponse": (".runtime", "RuntimeAPIResponse"),
    "RuntimeAuditRecord": (".runtime", "RuntimeAuditRecord"),
    "RuntimeActionRequest": (".runtime", "RuntimeActionRequest"),
    "RuntimeCommandRouter": (".runtime", "RuntimeCommandRouter"),
    "RuntimeTUIView": (".runtime", "RuntimeTUIView"),
    "RuntimeWebRouter": (".runtime", "RuntimeWebRouter"),
    "RuntimeActionDecision": (".runtime", "RuntimeActionDecision"),
    "RuntimeActionEffect": (".runtime", "RuntimeActionEffect"),
    "RuntimeActionPolicy": (".runtime", "RuntimeActionPolicy"),
    "RuntimeAuthError": (".runtime", "RuntimeAuthError"),
    "RuntimePrincipal": (".runtime", "RuntimePrincipal"),
    "RuntimeTokenAuthority": (".runtime", "RuntimeTokenAuthority"),
    "RuntimeStoreBundle": (".runtime", "RuntimeStoreBundle"),
    "RuntimeInterface": (".runtime", "RuntimeInterface"),
    "run_coding_workflow": (".runtime", "run_coding_workflow"),
    "run_refactor_workflow": (".runtime", "run_refactor_workflow"),
    "RunEventType": (".runtime", "RunEventType"),
    "ActorRef": (".runtime", "ActorRef"),
    "InMemoryApprovalStore": (".runtime", "InMemoryApprovalStore"),
    "InMemoryArtifactStore": (".runtime", "InMemoryArtifactStore"),
    "InMemoryCheckpointStore": (".runtime", "InMemoryCheckpointStore"),
    "human_approval_node_handler": (".runtime", "human_approval_node_handler"),
    "InMemoryTraceStore": (".runtime", "InMemoryTraceStore"),
    "InMemoryRunStore": (".runtime", "InMemoryRunStore"),
    "InMemoryRuntimeAuditStore": (".runtime", "InMemoryRuntimeAuditStore"),
    "EvaluationMetric": (".runtime", "EvaluationMetric"),
    "EvaluationResult": (".runtime", "EvaluationResult"),
    "MultiAgentCoordinator": (".runtime", "MultiAgentCoordinator"),
    "QualityGate": (".runtime", "QualityGate"),
    "QualityGateDecision": (".runtime", "QualityGateDecision"),
    "QualityGateRunner": (".runtime", "QualityGateRunner"),
    "QualityGateStatus": (".runtime", "QualityGateStatus"),
    "SQLiteApprovalStore": (".runtime", "SQLiteApprovalStore"),
    "SQLiteArtifactStore": (".runtime", "SQLiteArtifactStore"),
    "SQLiteCheckpointStore": (".runtime", "SQLiteCheckpointStore"),
    "SQLiteTraceStore": (".runtime", "SQLiteTraceStore"),
    "SQLiteRunStore": (".runtime", "SQLiteRunStore"),
    "SQLiteRuntimeAuditStore": (".runtime", "SQLiteRuntimeAuditStore"),
    "CheckpointRecord": (".runtime", "CheckpointRecord"),
    "DebugFrame": (".runtime", "DebugFrame"),
    "coding_workflow_template": (".runtime", "coding_workflow_template"),
    "queued_human_approval_node_handler": (".runtime", "queued_human_approval_node_handler"),
    "refactor_workflow_template": (".runtime", "refactor_workflow_template"),
    "RunRecord": (".runtime", "RunRecord"),
    "RunStatus": (".runtime", "RunStatus"),
    "StepRecord": (".runtime", "StepRecord"),
    "StepStatus": (".runtime", "StepStatus"),
    "StepType": (".runtime", "StepType"),
    "static_approval_backend": (".runtime", "static_approval_backend"),
    "tool_mapping_backend": (".runtime", "tool_mapping_backend"),
    "registry_tool_backend": (".runtime", "registry_tool_backend"),
    "ToolExecutionDenied": (".runtime", "ToolExecutionDenied"),
    "ToolPolicy": (".runtime", "ToolPolicy"),
    "ToolRegistry": (".runtime", "ToolRegistry"),
    "tool_node_handler": (".runtime", "tool_node_handler"),
    "ToolSpec": (".runtime", "ToolSpec"),
    "RunTimeline": (".runtime", "RunTimeline"),
    "TimelineAPI": (".runtime", "TimelineAPI"),
    "TimelineItem": (".runtime", "TimelineItem"),
    "CompiledWorkflow": (".runtime", "CompiledWorkflow"),
    "Workflow": (".runtime", "Workflow"),
    "WorkflowCancelled": (".runtime", "WorkflowCancelled"),
    "WorkflowControlState": (".runtime", "WorkflowControlState"),
    "WorkflowExecutionError": (".runtime", "WorkflowExecutionError"),
    "WorkflowPaused": (".runtime", "WorkflowPaused"),
    "WorkflowWaiting": (".runtime", "WorkflowWaiting"),
    "WorkflowRunManager": (".runtime", "WorkflowRunManager"),
    "WorkflowRunManagerError": (".runtime", "WorkflowRunManagerError"),
    "WorkflowScheduleError": (".runtime", "WorkflowScheduleError"),
    "WorkflowScheduler": (".runtime", "WorkflowScheduler"),
    "WorkflowExecutor": (".runtime", "WorkflowExecutor"),
    "WorkflowEdge": (".runtime", "WorkflowEdge"),
    "WorkflowEdgeType": (".runtime", "WorkflowEdgeType"),
    "WorkflowNode": (".runtime", "WorkflowNode"),
    "WorkflowNodeType": (".runtime", "WorkflowNodeType"),
    "WorkflowState": (".runtime", "WorkflowState"),
    "stream_event_to_run_event": (".runtime", "stream_event_to_run_event"),
    # log
    "setup_logging": (".log", "setup_logging"),
    # model_resolver
    "resolve_model": (".model_resolver", "resolve_model"),
    "resolve_small_model": (".model_resolver", "resolve_small_model"),
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
