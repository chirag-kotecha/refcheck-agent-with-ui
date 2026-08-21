"""
Unit tests for config.get_model (generic provider/tier model resolution)
and llm.providers.get_provider (dynamic provider selection). No network,
no API key needed.

Run with: pytest tests/test_config_and_providers.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from refcheck import config


def test_get_model_returns_configured_default():
    assert config.get_model("anthropic", "extraction") == "claude-haiku-4-5"
    assert config.get_model("anthropic", "reasoning") == "claude-sonnet-4-6"


def test_get_model_different_providers_return_different_id_formats():
    anthropic_id = config.get_model("anthropic", "reasoning")
    bedrock_id = config.get_model("bedrock", "reasoning")
    openrouter_id = config.get_model("openrouter", "reasoning")
    assert anthropic_id != bedrock_id != openrouter_id
    assert bedrock_id.startswith("anthropic.")
    assert "/" in openrouter_id


def test_get_model_unknown_provider_raises():
    with pytest.raises(ValueError):
        config.get_model("not-a-real-provider", "extraction")


def test_get_model_unknown_tier_raises():
    with pytest.raises(ValueError):
        config.get_model("anthropic", "not-a-real-tier")


def test_get_model_env_var_override(monkeypatch):
    monkeypatch.setenv("MODEL_ANTHROPIC_EXTRACTION", "claude-custom-test-model")
    assert config.get_model("anthropic", "extraction") == "claude-custom-test-model"


def test_get_model_bedrock_env_var_override(monkeypatch):
    monkeypatch.setenv("MODEL_BEDROCK_REASONING", "anthropic.custom-test-model-v1:0")
    assert config.get_model("bedrock", "reasoning") == "anthropic.custom-test-model-v1:0"


def test_get_provider_unknown_name_raises():
    from refcheck.llm.providers import get_provider
    with pytest.raises(ValueError):
        get_provider("not-a-real-provider")


def test_get_provider_anthropic_resolves_to_correct_class(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    from refcheck.llm.providers import get_provider
    provider = get_provider("anthropic")
    assert provider.PROVIDER_NAME == "anthropic"
    assert provider.get_model("reasoning") == config.get_model("anthropic", "reasoning")
