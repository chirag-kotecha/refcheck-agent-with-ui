"""
Abstract base class for LLM provider backends. All shared orchestration
(retry, timeout handling, forced structured output, schema validation,
logging) lives here in `structured_call`. Each subclass implements only
the three genuinely provider-specific pieces: `_execute`,
`_extract_tool_input`, `_is_retryable_exception`.
"""

import time
from abc import ABC, abstractmethod
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError as PydanticValidationError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential, before_sleep_log

from refcheck import config
from refcheck.logging_config import get_logger

T = TypeVar("T", bound=BaseModel)


class StructuredCallError(RuntimeError):
    """Raised when a provider doesn't return the expected tool call, or
    returns output that fails schema validation, after all retries."""


class BaseLLMProvider(ABC):
    PROVIDER_NAME: str = None

    def __init__(self):
        if not self.PROVIDER_NAME:
            raise NotImplementedError(f"{type(self).__name__} must set PROVIDER_NAME")
        self.logger = get_logger(f"llm.{self.PROVIDER_NAME}")

    def get_model(self, tier: str) -> str:
        """Resolves a tier name ("extraction" / "reasoning") to this
        provider's concrete model ID. See config.get_model."""
        return config.get_model(self.PROVIDER_NAME, tier)

    def structured_call(
        self,
        system: str,
        user_message: str,
        output_model: Type[T],
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        enable_cache: bool = False,
    ) -> T:
        max_tokens = max_tokens or config.LLM_MAX_TOKENS
        model = model or self.get_model("reasoning")
        tool_name = f"emit_{output_model.__name__.lower()}"
        schema = output_model.model_json_schema()
        schema.pop("title", None)

        retryer = Retrying(
            retry=retry_if_exception(self._is_retryable_exception),
            stop=stop_after_attempt(config.LLM_MAX_RETRIES),
            wait=wait_exponential(
                multiplier=config.LLM_RETRY_BASE_SECONDS, max=config.LLM_RETRY_MAX_WAIT_SECONDS
            ),
            before_sleep=before_sleep_log(self.logger, 30),
            reraise=True,
        )

        start = time.monotonic()
        try:
            response = retryer(
                self._execute,
                model=model, system=system, user_message=user_message,
                tool_name=tool_name, schema=schema, max_tokens=max_tokens,
                enable_cache=enable_cache,
            )
        except Exception as e:
            if self._is_retryable_exception(e):
                self.logger.error(
                    f"structured_call failed after retries: tool={tool_name} "
                    f"model={model} error={e!r}"
                )
                raise StructuredCallError(
                    f"{self.PROVIDER_NAME} call failed after retries: {e}"
                ) from e
            raise

        elapsed_ms = int((time.monotonic() - start) * 1000)

        tool_input = self._extract_tool_input(response, tool_name)
        if tool_input is None:
            self.logger.error(f"missing expected tool call: tool={tool_name} model={model}")
            raise StructuredCallError(
                f"{self.PROVIDER_NAME} did not return the expected tool call ({tool_name})."
            )

        try:
            result = output_model.model_validate(tool_input)
        except PydanticValidationError as e:
            self.logger.error(f"schema validation failed: tool={tool_name} error={e!r}")
            raise StructuredCallError(
                f"Model output for {output_model.__name__} failed schema validation: {e}"
            ) from e

        self._log_success(tool_name, model, elapsed_ms, response)
        return result

    def _log_success(self, tool_name: str, model: str, elapsed_ms: int, response) -> None:
        self.logger.info(f"structured_call ok: tool={tool_name} model={model} elapsed_ms={elapsed_ms}")

    @abstractmethod
    def _is_retryable_exception(self, exc: Exception) -> bool:
        raise NotImplementedError

    @abstractmethod
    def _execute(self, *, model: str, system: str, user_message: str, tool_name: str,
                 schema: dict, max_tokens: int, enable_cache: bool):
        raise NotImplementedError

    @abstractmethod
    def _extract_tool_input(self, response, tool_name: str) -> Optional[dict]:
        raise NotImplementedError

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text) // 4
