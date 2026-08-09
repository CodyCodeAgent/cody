"""Built-in workflow templates for common software-engineering tasks."""

from __future__ import annotations

from .workflow import Workflow, WorkflowEdgeType, WorkflowNodeType


def coding_workflow_template(*, workflow_id: str = "workflow_coding") -> Workflow:
    """Return a standard plan → implement → test → review → approve workflow.

    The template is intentionally backend-neutral. Runtime users can attach
    `agent_node_handler`, `tool_node_handler`, and `human_approval_node_handler`
    to execute the nodes with their chosen AgentRunner/tool/approval backends.
    """

    return (
        Workflow("coding", workflow_id=workflow_id, metadata={"template": "coding", "version": 1})
        .node(
            "plan",
            WorkflowNodeType.AGENT,
            name="Plan implementation",
            agent_name="planner",
            metadata={"prompt": "Create an implementation plan with acceptance criteria."},
        )
        .node(
            "implement",
            WorkflowNodeType.AGENT,
            name="Implement changes",
            agent_name="code",
            metadata={"prompt": "Implement the approved plan."},
        )
        .node(
            "test",
            WorkflowNodeType.TOOL,
            name="Run tests",
            tool_name="exec_command",
            metadata={"args": {"command": "pytest"}},
        )
        .node(
            "fix",
            WorkflowNodeType.AGENT,
            name="Fix failing tests",
            agent_name="code",
            metadata={"prompt": "Fix the failing tests and preserve behavior."},
        )
        .node(
            "review",
            WorkflowNodeType.AGENT,
            name="Review implementation",
            agent_name="review",
            metadata={"prompt": "Review the final diff for correctness, safety, and maintainability."},
        )
        .node(
            "approval",
            WorkflowNodeType.HUMAN_APPROVAL,
            name="Human approval",
            metadata={"request": {"action": "approve_final_diff"}},
        )
        .edge("plan", "implement")
        .edge("implement", "test")
        .conditional_edge("test", "fix", condition="tests_failed", label="fix failures")
        .edge("test", "review", edge_type=WorkflowEdgeType.SEQUENTIAL, label="tests passed")
        .edge("fix", "test", edge_type=WorkflowEdgeType.SEQUENTIAL, label="re-test")
        .conditional_edge("review", "fix", condition="review_requested_changes", label="address review")
        .edge("review", "approval")
    )


def refactor_workflow_template(*, workflow_id: str = "workflow_refactor") -> Workflow:
    """Return a standard architecture-first refactor workflow."""

    return (
        Workflow("refactor", workflow_id=workflow_id, metadata={"template": "refactor", "version": 1})
        .node(
            "analyze",
            WorkflowNodeType.AGENT,
            name="Analyze architecture",
            agent_name="architect",
            metadata={"prompt": "Analyze the current architecture and identify refactor boundaries."},
        )
        .node(
            "safety_tests",
            WorkflowNodeType.AGENT,
            name="Add safety tests",
            agent_name="test",
            metadata={"prompt": "Add or identify safety tests before refactoring."},
        )
        .node(
            "refactor",
            WorkflowNodeType.AGENT,
            name="Refactor implementation",
            agent_name="code",
            metadata={"prompt": "Perform the refactor incrementally."},
        )
        .node(
            "test",
            WorkflowNodeType.TOOL,
            name="Run tests",
            tool_name="exec_command",
            metadata={"args": {"command": "pytest"}},
        )
        .node(
            "review",
            WorkflowNodeType.AGENT,
            name="Review refactor",
            agent_name="review",
            metadata={"prompt": "Review behavior preservation and maintainability."},
        )
        .edge("analyze", "safety_tests")
        .edge("safety_tests", "refactor")
        .edge("refactor", "test")
        .conditional_edge("test", "refactor", condition="tests_failed", label="fix failures")
        .edge("test", "review", label="tests passed")
    )
