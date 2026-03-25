"""Tests for custom system prompt API (#8)."""

from unittest.mock import MagicMock, patch

from cody.core.config import Config
from cody.core.runner import AgentRunner


# ── Runner-level tests ───────────────────────────────────────────────────────


class TestRunnerSystemPrompt:
    def test_default_no_override(self, tmp_path):
        """Without system_prompt, base persona is used."""
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(config=Config(), workdir=tmp_path)
        assert runner._system_prompt_override is None
        assert runner._extra_system_prompt is None

    def test_system_prompt_stored(self, tmp_path):
        """system_prompt override is stored."""
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(),
                workdir=tmp_path,
                system_prompt="You are a code reviewer.",
            )
        assert runner._system_prompt_override == "You are a code reviewer."

    def test_extra_system_prompt_stored(self, tmp_path):
        """extra_system_prompt is stored."""
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(),
                workdir=tmp_path,
                extra_system_prompt="Always respond in Chinese.",
            )
        assert runner._extra_system_prompt == "Always respond in Chinese."

    def test_system_prompt_replaces_persona(self, tmp_path):
        """When system_prompt is set, _create_agent uses it instead of base persona."""
        runner_cls = AgentRunner
        with patch.object(runner_cls, "__init__", lambda self, **kw: None):
            runner = runner_cls.__new__(runner_cls)
            runner.config = Config()
            runner.workdir = tmp_path
            runner._custom_tools = []
            runner._system_prompt_override = "Custom persona."
            runner._extra_system_prompt = None
            runner._mcp_client = None
            runner._memory_store = None
            runner.skill_manager = MagicMock()
            runner.skill_manager.to_prompt_xml.return_value = ""

        with patch("cody.core.runner.Agent") as MockAgent, \
             patch("cody.core.runner.tools") as _mock_tools, \
             patch("cody.core.runner.load_project_instructions", return_value=""), \
             patch.object(runner, "_resolve_model", return_value=MagicMock()):
            MockAgent.return_value = MagicMock()
            runner._create_agent()
            # Verify system_prompt passed to Agent starts with custom persona
            call_kwargs = MockAgent.call_args[1]
            assert call_kwargs["system_prompt"].startswith("Custom persona.")

    def test_extra_system_prompt_appended(self, tmp_path):
        """extra_system_prompt is appended at the end."""
        runner_cls = AgentRunner
        with patch.object(runner_cls, "__init__", lambda self, **kw: None):
            runner = runner_cls.__new__(runner_cls)
            runner.config = Config()
            runner.workdir = tmp_path
            runner._custom_tools = []
            runner._system_prompt_override = None
            runner._extra_system_prompt = "EXTRA INSTRUCTIONS HERE"
            runner._mcp_client = None
            runner._memory_store = None
            runner.skill_manager = MagicMock()
            runner.skill_manager.to_prompt_xml.return_value = ""

        with patch("cody.core.runner.Agent") as MockAgent, \
             patch("cody.core.runner.tools") as _mock_tools, \
             patch("cody.core.runner.load_project_instructions", return_value=""), \
             patch.object(runner, "_resolve_model", return_value=MagicMock()):
            MockAgent.return_value = MagicMock()
            runner._create_agent()
            call_kwargs = MockAgent.call_args[1]
            assert call_kwargs["system_prompt"].endswith("EXTRA INSTRUCTIONS HERE")

    def test_both_overrides(self, tmp_path):
        """Both system_prompt and extra_system_prompt work together."""
        runner_cls = AgentRunner
        with patch.object(runner_cls, "__init__", lambda self, **kw: None):
            runner = runner_cls.__new__(runner_cls)
            runner.config = Config()
            runner.workdir = tmp_path
            runner._custom_tools = []
            runner._system_prompt_override = "Custom persona."
            runner._extra_system_prompt = "Extra context."
            runner._mcp_client = None
            runner._memory_store = None
            runner.skill_manager = MagicMock()
            runner.skill_manager.to_prompt_xml.return_value = ""

        with patch("cody.core.runner.Agent") as MockAgent, \
             patch("cody.core.runner.tools") as _mock_tools, \
             patch("cody.core.runner.load_project_instructions", return_value=""), \
             patch.object(runner, "_resolve_model", return_value=MagicMock()):
            MockAgent.return_value = MagicMock()
            runner._create_agent()
            call_kwargs = MockAgent.call_args[1]
            prompt = call_kwargs["system_prompt"]
            assert prompt.startswith("Custom persona.")
            assert prompt.endswith("Extra context.")


# ── SDK Builder-level tests ──────────────────────────────────────────────────


class TestBuilderSystemPrompt:
    def test_system_prompt_method(self):
        from cody.sdk.client import CodyBuilder
        builder = CodyBuilder()
        result = builder.system_prompt("You are a reviewer.")
        assert result is builder
        assert builder._system_prompt == "You are a reviewer."

    def test_extra_system_prompt_method(self):
        from cody.sdk.client import CodyBuilder
        builder = CodyBuilder()
        result = builder.extra_system_prompt("Respond in Chinese.")
        assert result is builder
        assert builder._extra_system_prompt == "Respond in Chinese."

    def test_builder_passes_prompts_to_client(self):
        from cody.sdk.client import Cody, AsyncCodyClient
        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            Cody().system_prompt("custom").extra_system_prompt("extra").build()
            _, kwargs = mock_init.call_args
            assert kwargs["system_prompt"] == "custom"
            assert kwargs["extra_system_prompt"] == "extra"

    def test_builder_defaults_none(self):
        from cody.sdk.client import Cody, AsyncCodyClient
        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            Cody().build()
            _, kwargs = mock_init.call_args
            assert kwargs["system_prompt"] is None
            assert kwargs["extra_system_prompt"] is None
