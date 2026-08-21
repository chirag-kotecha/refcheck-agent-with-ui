"""OpenRouter provider (real-time, synchronous calls)."""

import json
import os
from typing import Optional

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from refcheck import config
from refcheck.llm.base import BaseLLMProvider, StructuredCallError  # re-exported

__all__ = ["OpenRouterProvider", "StructuredCallError"]


class OpenRouterProvider(BaseLLMProvider):
    PROVIDER_NAME = "openrouter"

    def __init__(self):
        super().__init__()
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            timeout=config.LLM_TIMEOUT_SECONDS,
        )

    def _is_retryable_exception(self, exc: Exception) -> bool:
        return isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError))

    def _build_system_message(self, system: str, enable_cache: bool) -> dict:
        if not enable_cache:
            return {"role": "system", "content": system}
        estimated = self._estimate_tokens(system)
        if estimated < config.PROMPT_CACHE_MIN_TOKENS_ESTIMATE:
            self.logger.warning(
                f"prompt caching requested but system prompt (~{estimated} tokens) is "
                f"likely below the cacheable minimum; may have no effect and/or may not "
                f"be supported depending on the routed model"
            )
        return {
            "role": "system",
            "content": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        }

    def _execute(self, *, model, system, user_message, tool_name, schema, max_tokens, enable_cache):
        return self.client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                self._build_system_message(system, enable_cache),
                {"role": "user", "content": user_message},
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": "Emit the extracted result as the requested schema.",
                    "parameters": schema,
                },
            }],
            tool_choice={"type": "function", "function": {"name": tool_name}},
        )

    def _extract_tool_input(self, response, tool_name: str) -> Optional[dict]:
        message = response.choices[0].message
        if not message.tool_calls:
            return None
        for call in message.tool_calls:
            if call.function.name == tool_name:
                try:
                    return json.loads(call.function.arguments)
                except json.JSONDecodeError as e:
                    self.logger.warning(f"tool_call arguments were not valid JSON: {e!r}")
                    return None
        return None

    def _log_success(self, tool_name, model, elapsed_ms, response):
        usage = getattr(response, "usage", None)
        cache_info = getattr(usage, "cache_read_input_tokens", None) if usage else None
        self.logger.info(
            f"structured_call ok: tool={tool_name} model={model} elapsed_ms={elapsed_ms} "
            f"cache_read_tokens={cache_info}"
        )
