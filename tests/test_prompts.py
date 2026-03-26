"""Tests for core/prompts.py — system prompt construction."""

from cody.core.prompts import build_system_prompt


class TestBuildSystemPrompt:
    """Verify that build_system_prompt() produces a complete prompt."""

    def test_returns_string(self):
        result = build_system_prompt()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_role_definition(self):
        result = build_system_prompt()
        assert "You are Cody" in result

    def test_contains_capabilities(self):
        result = build_system_prompt()
        assert "## Capabilities" in result
        assert "file operations" in result
        assert "shell command execution" in result
        assert "sub-agent spawning" in result

    def test_contains_boundaries(self):
        result = build_system_prompt()
        assert "## Boundaries" in result
        assert "NEVER delete files outside the project directory" in result
        assert "NEVER modify system files" in result
        assert "NEVER run destructive commands" in result

    def test_contains_output_format(self):
        result = build_system_prompt()
        assert "## Output Format" in result
        assert "Markdown" in result

    def test_contains_code_quality(self):
        result = build_system_prompt()
        assert "## Code Quality" in result
        assert "Match existing code style" in result

    def test_contains_task_completion(self):
        result = build_system_prompt()
        assert "## Task Completion" in result
        assert "tests pass" in result

    def test_contains_context_management(self):
        result = build_system_prompt()
        assert "## Context Management" in result
        assert "save_memory()" in result

    def test_contains_thinking_guidance(self):
        result = build_system_prompt()
        assert "## Approach" in result
        assert "Understand" in result
        assert "Plan" in result
        assert "Execute" in result
        assert "Verify" in result
        assert "Report" in result
        assert "Do NOT skip step 1" in result

    def test_contains_sub_agent_guidance(self):
        result = build_system_prompt()
        assert "## Sub-Agent Parallelism" in result
        assert "spawn_agent()" in result

    def test_contains_skills_guidance(self):
        result = build_system_prompt()
        assert "## Skills Usage" in result
        assert "read_skill(skill_name)" in result
        assert "context overhead" in result

    def test_sections_order(self):
        """Verify sections appear in the expected order."""
        result = build_system_prompt()
        capabilities_pos = result.index("## Capabilities")
        approach_pos = result.index("## Approach")
        sub_agent_pos = result.index("## Sub-Agent Parallelism")
        skills_pos = result.index("## Skills Usage")

        assert capabilities_pos < approach_pos < sub_agent_pos < skills_pos
