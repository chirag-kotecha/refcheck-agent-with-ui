"""
AWS Bedrock batch inference backend.

Structurally very different from Anthropic's direct Batch API
(anthropic_batch.py): Bedrock's batch inference is S3-based, not
inline. You upload a JSONL file of requests to S3, call
CreateModelInvocationJob (control-plane `bedrock` client, NOT
`bedrock-runtime`), poll the job resource, then read result JSONL
file(s) back out of a different S3 location once it's done.

KEY CONSTRAINT: a Bedrock batch job runs against exactly ONE model --
there's no per-request model field like Anthropic's Batch API. If the
items you pass span multiple models (e.g. mixing extraction-tier and
reasoning-tier requests in one call), this module transparently splits
them into one job per distinct model and waits for all of them --
that's what submit_batch/wait_for_batch/fetch_batch_results do
internally. run_batch_sync hides this and exposes the same
`list[BatchItem] -> dict[custom_id, BatchItemResult]` shape as
anthropic_batch.run_batch_sync, so pipelines/batch_runner.py can treat
either backend uniformly.

REQUIRED SETUP (see .env.example):
  - config.BEDROCK_BATCH_S3_BUCKET       -- bucket for input/output JSONL
  - config.BEDROCK_BATCH_ROLE_ARN        -- IAM role the batch job assumes;
                                             must trust bedrock.amazonaws.com
                                             and have read on the input
                                             prefix + write on the output prefix
  - AWS credentials with permission to call bedrock:CreateModelInvocationJob,
    bedrock:GetModelInvocationJob, and s3:PutObject/GetObject/ListBucket
    on the configured bucket

IMPORTANT CAVEATS (unverified against a live call -- no network access
during development, same limitation as elsewhere in this codebase):
  - Method/field names (create_model_invocation_job, jobArn, status
    values, output record shape with "recordId"/"modelOutput") match
    Bedrock's documented batch inference API as of this codebase's last
    verification. Confirm against your boto3 version and
    https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html
    before relying on this in production.
  - Bedrock batch inference has documented minimum/maximum record counts
    per job (historically a few hundred minimum, tens of thousands
    maximum) that this module does NOT enforce -- it logs a warning if
    your item count looks low, but a real job below the minimum will be
    rejected by AWS at submission time. The small sample batches in this
    demo (a handful of items) are almost certainly below whatever the
    real minimum is; this module is written for correctness of shape,
    not for passing that minimum in the demo.
  - Output file naming under the output S3 prefix isn't fully
    predictable from the API alone, so this module lists everything
    under the job's output prefix and parses every .jsonl/.jsonl.out
    file it finds, rather than assuming one specific filename.
"""

import json
import os
import time
import uuid
from urllib.parse import urlparse

import boto3
from pydantic import ValidationError as PydanticValidationError

from refcheck import config
from refcheck.logging_config import get_logger
from refcheck.llm.batch.base import BatchItem, BatchItemResult, BatchError

logger = get_logger(__name__)

_region = os.environ.get("AWS_REGION", "us-east-1")
_bedrock_client = boto3.client("bedrock", region_name=_region)
_s3_client = boto3.client("s3")

MIN_RECOMMENDED_RECORDS = 100  # see module docstring -- not enforced, just warned about


def _require_config():
    missing = [
        name for name, val in [
            ("BEDROCK_BATCH_S3_BUCKET", config.BEDROCK_BATCH_S3_BUCKET),
            ("BEDROCK_BATCH_ROLE_ARN", config.BEDROCK_BATCH_ROLE_ARN),
        ] if not val
    ]
    if missing:
        raise BatchError(
            f"bedrock_batch.py requires the following config/env vars to be set: "
            f"{', '.join(missing)}. See .env.example."
        )


def _sanitize_record_id(custom_id: str) -> str:
    """Bedrock batch recordIds must be simple identifiers -- this
    project's custom_ids use ':' as a separator (e.g. 'c0:r1:extract'),
    which may not be accepted, so colons become underscores. Uniqueness
    is preserved since custom_ids in this codebase only ever differ by
    character in that position."""
    return custom_id.replace(":", "_")


def _build_model_input(item: BatchItem) -> dict:
    """Bedrock batch inference request body for an Anthropic model uses
    the native Anthropic Messages API request shape (same as
    InvokeModel), NOT the Converse API shape used by
    llm/bedrock_provider.py for real-time calls -- these are two
    different Bedrock API surfaces with different body formats."""
    max_tokens = item.max_tokens or config.LLM_MAX_TOKENS
    tool_name = f"emit_{item.output_model.__name__.lower()}"
    schema = item.output_model.model_json_schema()
    schema.pop("title", None)

    return {
        "anthropic_version": "bedrock-2023-05-31",
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


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip("/")


def _submit_single_model_job(model: str, items: list[BatchItem]) -> str:
    _require_config()
    if len(items) < MIN_RECOMMENDED_RECORDS:
        logger.warning(
            f"submitting a Bedrock batch job with only {len(items)} records for "
            f"model={model}; Bedrock enforces a minimum record count per job that "
            f"this is very likely below -- see module docstring. This will probably "
            f"be rejected by AWS if run for real; fine for demonstrating the code path."
        )

    job_name = f"{config.BEDROCK_BATCH_JOB_NAME_PREFIX}-{uuid.uuid4().hex[:12]}"
    lines = []
    for item in items:
        record = {"recordId": _sanitize_record_id(item.custom_id), "modelInput": _build_model_input(item)}
        lines.append(json.dumps(record))
    jsonl_body = "\n".join(lines).encode("utf-8")

    input_key = f"{config.BEDROCK_BATCH_S3_INPUT_PREFIX}/{job_name}.jsonl"
    output_prefix = f"{config.BEDROCK_BATCH_S3_OUTPUT_PREFIX}/{job_name}/"

    _s3_client.put_object(Bucket=config.BEDROCK_BATCH_S3_BUCKET, Key=input_key, Body=jsonl_body)
    logger.info(
        f"uploaded batch input: s3://{config.BEDROCK_BATCH_S3_BUCKET}/{input_key} "
        f"({len(items)} records, model={model})"
    )

    response = _bedrock_client.create_model_invocation_job(
        jobName=job_name,
        roleArn=config.BEDROCK_BATCH_ROLE_ARN,
        modelId=model,
        inputDataConfig={
            "s3InputDataConfig": {"s3Uri": f"s3://{config.BEDROCK_BATCH_S3_BUCKET}/{input_key}"}
        },
        outputDataConfig={
            "s3OutputDataConfig": {"s3Uri": f"s3://{config.BEDROCK_BATCH_S3_BUCKET}/{output_prefix}"}
        },
    )
    job_arn = response["jobArn"]
    logger.info(f"bedrock batch job submitted: job_arn={job_arn} model={model} job_name={job_name}")
    return job_arn


def submit_batch(items: list[BatchItem]) -> dict[str, str]:
    """Groups items by model (one Bedrock job per model) and submits
    one CreateModelInvocationJob per group. Returns {model: job_arn}."""
    if not items:
        raise ValueError("submit_batch called with an empty item list")

    by_model: dict[str, list[BatchItem]] = {}
    for item in items:
        by_model.setdefault(item.model, []).append(item)

    jobs = {}
    for model, model_items in by_model.items():
        jobs[model] = _submit_single_model_job(model, model_items)
    return jobs


def _wait_for_single_job(job_arn: str, poll_interval: float, max_wait: float) -> None:
    start = time.monotonic()
    while True:
        job = _bedrock_client.get_model_invocation_job(jobIdentifier=job_arn)
        status = job["status"]
        elapsed = time.monotonic() - start
        logger.info(f"bedrock batch poll: job_arn={job_arn} status={status} elapsed_s={int(elapsed)}")

        if status == "Completed":
            return
        if status in ("Failed", "Stopped"):
            raise BatchError(f"Bedrock batch job {job_arn} ended with status={status}: {job.get('message', '')}")
        if elapsed > max_wait:
            raise BatchError(
                f"Bedrock batch job {job_arn} did not finish within {max_wait}s "
                f"(status={status}); it may still complete -- check "
                f"get_model_invocation_job('{job_arn}') later."
            )
        time.sleep(poll_interval)


def wait_for_batch(jobs: dict[str, str], poll_interval: float = None, max_wait: float = None) -> None:
    poll_interval = poll_interval or config.BEDROCK_BATCH_POLL_INTERVAL_SECONDS
    max_wait = max_wait or config.BEDROCK_BATCH_MAX_WAIT_SECONDS
    for model, job_arn in jobs.items():
        _wait_for_single_job(job_arn, poll_interval, max_wait)


def _parse_record(record: dict, item: BatchItem, custom_id: str) -> BatchItemResult:
    if "modelOutput" not in record:
        error = record.get("error", "unknown error (no modelOutput in record)")
        return BatchItemResult(custom_id=custom_id, success=False, error=str(error))

    tool_name = f"emit_{item.output_model.__name__.lower()}"
    content = record["modelOutput"].get("content", [])
    for block in content:
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            try:
                value = item.output_model.model_validate(block["input"])
                return BatchItemResult(custom_id=custom_id, success=True, value=value)
            except PydanticValidationError as e:
                return BatchItemResult(
                    custom_id=custom_id, success=False, error=f"schema validation failed: {e}"
                )
    return BatchItemResult(
        custom_id=custom_id, success=False, error="model did not return expected tool call"
    )


def _fetch_single_job_results(job_arn: str, items_for_model: dict[str, BatchItem]) -> dict[str, BatchItemResult]:
    job = _bedrock_client.get_model_invocation_job(jobIdentifier=job_arn)
    output_s3_uri = job["outputDataConfig"]["s3OutputDataConfig"]["s3Uri"]
    bucket, prefix = _parse_s3_uri(output_s3_uri)

    recordid_to_customid = {_sanitize_record_id(cid): cid for cid in items_for_model}
    results: dict[str, BatchItemResult] = {}

    paginator = _s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not (key.endswith(".jsonl.out") or key.endswith(".jsonl")):
                continue
            body = _s3_client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
            for line in body.splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                record_id = record.get("recordId")
                custom_id = recordid_to_customid.get(record_id)
                if custom_id is None:
                    continue  # not one of ours, or already-sanitized id we don't recognize
                item = items_for_model[custom_id]
                results[custom_id] = _parse_record(record, item, custom_id)

    for custom_id in items_for_model:
        if custom_id not in results:
            logger.error(f"no output record found for custom_id={custom_id} in job_arn={job_arn}")
            results[custom_id] = BatchItemResult(
                custom_id=custom_id, success=False, error="no output record found for this custom_id"
            )
    return results


def fetch_batch_results(jobs: dict[str, str], items_by_custom_id: dict[str, BatchItem]) -> dict[str, BatchItemResult]:
    all_results: dict[str, BatchItemResult] = {}
    for model, job_arn in jobs.items():
        items_for_model = {
            cid: item for cid, item in items_by_custom_id.items() if item.model == model
        }
        all_results.update(_fetch_single_job_results(job_arn, items_for_model))
    return all_results


def run_batch_sync(items: list[BatchItem], poll_interval: float = None,
                    max_wait: float = None) -> dict[str, BatchItemResult]:
    """Convenience: submit + wait + fetch, hiding the multi-job-per-model
    detail. Same signature/return shape as anthropic_batch.run_batch_sync."""
    items_by_id = {i.custom_id: i for i in items}
    jobs = submit_batch(items)
    wait_for_batch(jobs, poll_interval=poll_interval, max_wait=max_wait)
    return fetch_batch_results(jobs, items_by_id)
