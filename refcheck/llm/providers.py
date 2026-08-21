"""
Factory for real-time LLM provider instances (batch backends are
selected separately -- see refcheck/pipelines/batch_runner.py and
refcheck/llm/batch/). Lazy imports so you don't need boto3/openai
installed unless you actually select that provider.
"""

from typing import Optional

from refcheck import config
from refcheck.llm.base import BaseLLMProvider


def get_provider(name: Optional[str] = None) -> BaseLLMProvider:
    """
    Instantiates a provider by name: "anthropic", "bedrock", or
    "openrouter". Defaults to config.DEFAULT_LLM_PROVIDER (the
    LLM_PROVIDER env var). This is the single switch that determines
    which backend the real-time graphs talk to.
    """
    name = (name or config.DEFAULT_LLM_PROVIDER).lower()

    if name == "anthropic":
        from refcheck.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    elif name == "bedrock":
        from refcheck.llm.bedrock_provider import BedrockProvider
        return BedrockProvider()
    elif name == "openrouter":
        from refcheck.llm.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER={name!r}. Expected one of: anthropic, bedrock, openrouter."
        )
