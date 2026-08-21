"""
Anthropic Message Batches API backend. Submit many structured-output
requests as one batch job (inline, no S3 involved -- contrast with
bedrock_batch.py). Model IDs should come from config.get_model("anthropic", tier).

IMPORTANT: the Batch API surface (client.messages.batches.*) has
changed across Anthropic SDK versions and hasn't been verified against
a live call in this development environment (no network access). Method
names (create/retrieve/results) and field names (processing_status,
custom_id, result.type) match the documented API as of this codebase's
last verification -- confirm against your installed `anthropic` package
and https://docs.anthropic.com/en/docs/build-with-claude/batch-processing
before relying on this in production.
"""

import time

import anthropic
from pydantic import ValidationError as PydanticValidationError

from refcheck import config
from refcheck.logging_config import get_logger
from refcheck.llm.batch.base import BatchItem, BatchItemResult, BatchError

logger = get_logger(__name__)

client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY from env


def _build_params(item: BatchItem) -> dict:
    max_tokens = item.max_tokens or config.LLM_MAX_TOKENS
    tool_name = f"emit_{item.output_model.__name__.lower()}"
    schema = item.output_model.model_json_schema()
    schema.pop("title", None)

    return {
        "model": item.model,
        "max_tokens": max_tokens,
        "system": item.system,
        "messages": [{"role": "user", "content": item.user_message}],
        "tools": [{
            "name": tool_name,
            "description": f"Emit the extracted result as {item.output_model.__name__}.",
            "input_schema": schema,
        }],
        "tool_choice": {"type": "tool", "name": tool_name},
    }


def submit_batch(items: list[BatchItem]) -> str:
    if not items:
        raise ValueError("submit_batch called with an empty item list")
    custom_ids = [i.custom_id for i in items]
    if len(custom_ids) != len(set(custom_ids)):
        raise ValueError("custom_id values must be unique within a batch")

    requests = [{"custom_id": item.custom_id, "params": _build_params(item)} for item in items]
    batch = client.messages.batches.create(requests=requests)
    logger.info(f"batch submitted: batch_id={batch.id} n_requests={len(items)}")
    return batch.id


def wait_for_batch(batch_id: str, poll_interval: float = None, max_wait: float = None) -> None:
    poll_interval = poll_interval or config.BATCH_POLL_INTERVAL_SECONDS
    max_wait = max_wait or config.BATCH_MAX_WAIT_SECONDS

    start = time.monotonic()
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status
        elapsed = time.monotonic() - start
        logger.info(f"batch poll: batch_id={batch_id} status={status} elapsed_s={int(elapsed)}")

        if status == "ended":
            return
        if elapsed > max_wait:
            raise BatchError(
                f"Batch {batch_id} did not finish within {max_wait}s (status={status}); "
                f"it may still complete -- check client.messages.batches.retrieve('{batch_id}') later."
            )
        time.sleep(poll_interval)


def fetch_batch_results(batch_id: str, items_by_custom_id: dict[str, BatchItem]) -> dict[str, BatchItemResult]:
    results: dict[str, BatchItemResult] = {}

    for entry in client.messages.batches.results(batch_id):
        custom_id = entry.custom_id
        item = items_by_custom_id.get(custom_id)
        if item is None:
            logger.warning(f"batch result for unknown custom_id={custom_id}, skipping")
            continue

        if entry.result.type != "succeeded":
            error_msg = f"{entry.result.type}: {getattr(entry.result, 'error', '')}"
            logger.error(f"batch item failed: custom_id={custom_id} {error_msg}")
            results[custom_id] = BatchItemResult(custom_id=custom_id, success=False, error=error_msg)
            continue

        message = entry.result.message
        tool_name = f"emit_{item.output_model.__name__.lower()}"
        found = False
        for block in message.content:
            if block.type == "tool_use" and block.name == tool_name:
                try:
                    value = item.output_model.model_validate(block.input)
                    results[custom_id] = BatchItemResult(custom_id=custom_id, success=True, value=value)
                except PydanticValidationError as e:
                    logger.error(f"batch item schema validation failed: custom_id={custom_id} error={e!r}")
                    results[custom_id] = BatchItemResult(
                        custom_id=custom_id, success=False, error=f"schema validation failed: {e}"
                    )
                found = True
                break

        if not found:
            logger.error(f"batch item missing expected tool_use: custom_id={custom_id}")
            results[custom_id] = BatchItemResult(
                custom_id=custom_id, success=False, error="model did not return expected tool call"
            )

    for custom_id in items_by_custom_id:
        if custom_id not in results:
            logger.error(f"no batch result returned for custom_id={custom_id}")
            results[custom_id] = BatchItemResult(
                custom_id=custom_id, success=False, error="no result returned for this custom_id"
            )

    return results


def run_batch_sync(items: list[BatchItem], poll_interval: float = None,
                    max_wait: float = None) -> dict[str, BatchItemResult]:
    """Convenience: submit + wait + fetch in one call."""
    items_by_id = {i.custom_id: i for i in items}
    batch_id = submit_batch(items)
    wait_for_batch(batch_id, poll_interval=poll_interval, max_wait=max_wait)
    return fetch_batch_results(batch_id, items_by_id)
