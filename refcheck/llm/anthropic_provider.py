"""Anthropic direct-API provider (real-time, synchronous calls)."""

import os
from typing import Optional

import anthropic

from refcheck import config
from refcheck.llm.base import BaseLLMProvider, StructuredCallError  # re-exported

__all__ = ["AnthropicProvider", "StructuredCallError"]


class AnthropicProvider(BaseLLMProvider):
    PROVIDER_NAME = "anthropic"

    def __init__(self):
        super().__init__()
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            timeout=config.LLM_TIMEOUT_SECONDS,
        )

    def _is_retryable_exception(self, exc: Exception) -> bool:
        return isinstance(exc, (
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
        ))

    def _build_system_param(self, system: str, enable_cache: bool):
        if not enable_cache:
            return system
        estimated = self._estimate_tokens(system)
        if estimated < config.PROMPT_CACHE_MIN_TOKENS_ESTIMATE:
            self.logger.warning(
                f"prompt caching requested but system prompt (~{estimated} tokens) "
                f"is likely below the cacheable minimum "
                f"(~{config.PROMPT_CACHE_MIN_TOKENS_ESTIMATE}); may have no effect"
            )
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    def _execute(self, *, model, system, user_message, tool_name, schema, max_tokens, enable_cache):
        return self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=self._build_system_param(system, enable_cache),
            messages=[{"role": "user", "content": user_message}],
            tools=[{
                "name": tool_name,
                "description": "Emit the extracted result as the requested schema.",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
        )

    def _extract_tool_input(self, response, tool_name: str) -> Optional[dict]:
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input
        return None

    def _log_success(self, tool_name, model, elapsed_ms, response):
        usage = getattr(response, "usage", None)
        cache_read = getattr(usage, "cache_read_input_tokens", None) if usage else None
        cache_created = getattr(usage, "cache_creation_input_tokens", None) if usage else None
        self.logger.info(
            f"structured_call ok: tool={tool_name} model={model} elapsed_ms={elapsed_ms} "
            f"cache_read_tokens={cache_read} cache_created_tokens={cache_created}"
        )
