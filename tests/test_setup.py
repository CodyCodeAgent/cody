"""Tests for setup wizard helpers"""

from cody.core.setup import SetupAnswers, build_config_from_answers


def test_build_config_from_answers_anthropic():
    """Anthropic provider generates correct config dict"""
    answers = SetupAnswers(
        provider="anthropic",
        model="anthropic:claude-sonnet-4-0",
        model_api_key="sk-ant-test",
    )
    data = build_config_from_answers(answers)
    assert data["model"] == "anthropic:claude-sonnet-4-0"
    assert data["model_api_key"] == "sk-ant-test"
    assert "model_base_url" not in data
    assert "enable_thinking" not in data


def test_build_config_from_answers_custom():
    """Custom provider generates correct config dict with base_url"""
    answers = SetupAnswers(
        provider="custom",
        model="qwen3.5",
        model_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model_api_key="sk-sp-test",
    )
    data = build_config_from_answers(answers)
    assert data["model"] == "qwen3.5"
    assert data["model_base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert data["model_api_key"] == "sk-sp-test"


def test_build_config_from_answers_with_thinking():
    """Thinking mode is included when enabled"""
    answers = SetupAnswers(
        provider="anthropic",
        model="anthropic:claude-sonnet-4-0",
        model_api_key="sk-test",
        enable_thinking=True,
        thinking_budget=10000,
    )
    data = build_config_from_answers(answers)
    assert data["enable_thinking"] is True
    assert data["thinking_budget"] == 10000


def test_build_config_from_answers_without_thinking():
    """Thinking mode is excluded when disabled"""
    answers = SetupAnswers(
        provider="anthropic",
        model="anthropic:claude-sonnet-4-0",
        model_api_key="sk-test",
        enable_thinking=False,
    )
    data = build_config_from_answers(answers)
    assert "enable_thinking" not in data
    assert "thinking_budget" not in data


def test_build_config_from_answers_no_api_key():
    """Config without api_key omits it from dict"""
    answers = SetupAnswers(
        provider="anthropic",
        model="anthropic:claude-sonnet-4-0",
    )
    data = build_config_from_answers(answers)
    assert data["model"] == "anthropic:claude-sonnet-4-0"
    assert "model_api_key" not in data
