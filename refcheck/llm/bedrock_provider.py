"""
AWS Bedrock provider (Converse API, real-time synchronous calls). For
bulk/offline batch processing on Bedrock, see
refcheck/llm/batch/bedrock_batch.py -- that's a materially different
API (S3-based), not this one.

Setup: pip install boto3; configure AWS credentials via the default
boto3 credential chain; set AWS_REGION. Verify config.MODEL_TIERS
Bedrock IDs against your account's enabled models before relying on them.
"""

import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError, ConnectionError as BotoConnectionError

from refcheck import config
from refcheck.llm.base import BaseLLMProvider, StructuredCallError  # re-exported

__all__ = ["BedrockProvider", "StructuredCallError"]

_RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelTimeoutException",
}


class BedrockProvider(BaseLLMProvider):
    PROVIDER_NAME = "bedrock"

    def __init__(self):
        super().__init__()
        boto_config = None
        try:
            from botocore.config import Config as BotoConfig
            boto_config = BotoConfig(
                read_timeout=config.LLM_TIMEOUT_SECONDS,
                connect_timeout=config.LLM_TIMEOUT_SECONDS,
                retries={"max_attempts": 0},
            )
        except ImportError:
            pass
        region = os.environ.get("AWS_REGION", "us-east-1")
        self.client = boto3.client("bedrock-runtime", region_name=region, config=boto_config)

    def _is_retryable_exception(self, exc: Exception) -> bool:
        if isinstance(exc, BotoConnectionError):
            return True
        if isinstance(exc, ClientError):
            return exc.response.get("Error", {}).get("Code") in _RETRYABLE_ERROR_CODES
        return False

    def _build_system_param(self, system: str, enable_cache: bool) -> list:
        blocks = [{"text": system}]
        if enable_cache:
            estimated = self._estimate_tokens(system)
            if estimated < config.PROMPT_CACHE_MIN_TOKENS_ESTIMATE:
                self.logger.warning(
                    f"prompt caching requested but system prompt (~{estimated} tokens) "
                    f"is likely below the cacheable minimum "
                    f"(~{config.PROMPT_CACHE_MIN_TOKENS_ESTIMATE}); may have no effect"
                )
            blocks.append({"cachePoint": {"type": "default"}})
        return blocks

    def _execute(self, *, model, system, user_message, tool_name, schema, max_tokens, enable_cache):
        return self.client.converse(
            modelId=model,
            system=self._build_system_param(system, enable_cache),
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            toolConfig={
                "tools": [{
                    "toolSpec": {
                        "name": tool_name,
                        "description": "Emit the extracted result as the requested schema.",
                        "inputSchema": {"json": schema},
                    }
                }],
                "toolChoice": {"tool": {"name": tool_name}},
            },
            inferenceConfig={"maxTokens": max_tokens},
        )

    def _extract_tool_input(self, response, tool_name: str) -> Optional[dict]:
        output_message = response["output"]["message"]
        for block in output_message["content"]:
            if "toolUse" in block and block["toolUse"]["name"] == tool_name:
                return block["toolUse"]["input"]
        return None

    def _log_success(self, tool_name, model, elapsed_ms, response):
        usage = response.get("usage", {})
        self.logger.info(
            f"structured_call ok: tool={tool_name} model={model} elapsed_ms={elapsed_ms} "
            f"cache_read_tokens={usage.get('cacheReadInputTokens')} "
            f"cache_written_tokens={usage.get('cacheWriteInputTokens')}"
        )
