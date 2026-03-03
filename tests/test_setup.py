"""Tests for setup wizard helpers"""

from cody.core.setup import SetupAnswers, build_config_from_answers


def test_build_config_from_answers_no_base_url():
    """Without base_url, config has model + api_key only"""
    answers = SetupAnswers(
        model="anthropic:claude-sonnet-4-0",
        model_api_key="sk-ant-test",
    )
    data = build_config_from_answers(answers)
    assert data["model"] == "anthropic:claude-sonnet-4-0"
    assert data["model_api_key"] == "sk-ant-test"
    assert "model_base_url" not in data
    assert "enable_thinking" not in data


def test_build_config_from_answers_with_base_url():
    """With base_url, config includes all three fields"""
    answers = SetupAnswers(
        model="qwen3.5",
        model_api_key="sk-sp-test",
        model_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    data = build_config_from_answers(answers)
    assert data["model"] == "qwen3.5"
    assert data["model_base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert data["model_api_key"] == "sk-sp-test"


def test_build_config_from_answers_with_thinking():
    """Thinking mode is included when enabled"""
    answers = SetupAnswers(
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
        model="anthropic:claude-sonnet-4-0",
        model_api_key="sk-test",
        enable_thinking=False,
    )
    data = build_config_from_answers(answers)
    assert "enable_thinking" not in data
    assert "thinking_budget" not in data
