"""
Central configuration. Anything tunable without touching business logic
lives here -- scoring weights, thresholds, retry/timeout behavior,
concurrency limits, and model resolution.
"""

import os


# ---------------------------------------------------------------------------
# Scoring thresholds (single-reference)
# ---------------------------------------------------------------------------
MINOR_MONTH_TOLERANCE = int(os.environ.get("MINOR_MONTH_TOLERANCE", 1))
MODERATE_MONTH_TOLERANCE = int(os.environ.get("MODERATE_MONTH_TOLERANCE", 6))

SEVERITY_PENALTY = {
    "minor": int(os.environ.get("PENALTY_MINOR", 5)),
    "moderate": int(os.environ.get("PENALTY_MODERATE", 15)),
    "major": int(os.environ.get("PENALTY_MAJOR", 35)),
}
SENTIMENT_PENALTY = {
    "negative": int(os.environ.get("PENALTY_SENTIMENT_NEGATIVE", 20)),
    "mixed": int(os.environ.get("PENALTY_SENTIMENT_MIXED", 10)),
    "neutral": 0,
    "positive": 0,
}
RED_FLAG_PENALTY = int(os.environ.get("PENALTY_RED_FLAG", 10))
REVIEW_THRESHOLD = float(os.environ.get("REVIEW_THRESHOLD", 70))
OVERALL_REVIEW_THRESHOLD = float(os.environ.get("OVERALL_REVIEW_THRESHOLD", 70))

# ---------------------------------------------------------------------------
# Model tiering -- generic, provider-agnostic resolution. Two tiers:
#   "extraction" -- pattern-extraction tasks, cheaper/faster model is fine
#   "reasoning"  -- tasks needing more judgment
#
# get_model(provider, tier) is the ONLY place a model ID string is
# constructed. Every provider class (real-time AND batch) calls this
# with its own provider name -- node/pipeline code never hardcodes a
# model string. Override any entry via MODEL_<PROVIDER>_<TIER>.
# ---------------------------------------------------------------------------
MODEL_TIERS = {
    "anthropic": {
        "extraction": "claude-haiku-4-5",
        "reasoning": "claude-sonnet-4-6",
    },
    "bedrock": {
        "extraction": "amazon.nova-micro-v1:0",
        "reasoning": "amazon.nova-micro-v1:0",
    },
    "openrouter": {
        "extraction": "anthropic/claude-haiku-4.5",
        "reasoning": "anthropic/claude-sonnet-4.6",
    },
}


def get_model(provider: str, tier: str) -> str:
    """Resolves (provider, tier) -> a concrete model ID. Env var override
    checked first: MODEL_<PROVIDER>_<TIER>, e.g. MODEL_BEDROCK_REASONING.
    Used identically by real-time providers (llm/*_provider.py) and
    batch backends (llm/batch/*_batch.py) -- one resolution function for
    both execution paths."""
    env_key = f"MODEL_{provider.upper()}_{tier.upper()}"
    if env_key in os.environ:
        return os.environ[env_key]
    try:
        return MODEL_TIERS[provider][tier]
    except KeyError:
        raise ValueError(
            f"No model configured for provider={provider!r} tier={tier!r}. "
            f"Known providers: {list(MODEL_TIERS.keys())}. "
            f"Set env var {env_key} or add an entry to config.MODEL_TIERS."
        )


# ---------------------------------------------------------------------------
# LLM provider selection (real-time graphs)
# ---------------------------------------------------------------------------
DEFAULT_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "bedrock").lower()

# ---------------------------------------------------------------------------
# Prompt caching
# ---------------------------------------------------------------------------
ENABLE_PROMPT_CACHING = os.environ.get("ENABLE_PROMPT_CACHING", "false").lower() == "true"
PROMPT_CACHE_MIN_TOKENS_ESTIMATE = 1024

# ---------------------------------------------------------------------------
# LLM call behavior
# ---------------------------------------------------------------------------
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 1024))
LLM_TIMEOUT_SECONDS = float(os.environ.get("LLM_TIMEOUT_SECONDS", 30))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", 4))
LLM_RETRY_BASE_SECONDS = float(os.environ.get("LLM_RETRY_BASE_SECONDS", 1))
LLM_RETRY_MAX_WAIT_SECONDS = float(os.environ.get("LLM_RETRY_MAX_WAIT_SECONDS", 20))

# ---------------------------------------------------------------------------
# Concurrency / input validation
# ---------------------------------------------------------------------------
MAX_CONCURRENT_REFERENCES = int(os.environ.get("MAX_CONCURRENT_REFERENCES", 5))
MAX_RAW_INPUT_CHARS = int(os.environ.get("MAX_RAW_INPUT_CHARS", 20_000))
MIN_RAW_INPUT_CHARS = int(os.environ.get("MIN_RAW_INPUT_CHARS", 10))

# ---------------------------------------------------------------------------
# Batch API -- Anthropic direct (see refcheck/llm/batch/anthropic_batch.py)
# ---------------------------------------------------------------------------
BATCH_POLL_INTERVAL_SECONDS = float(os.environ.get("BATCH_POLL_INTERVAL_SECONDS", 15))
BATCH_MAX_WAIT_SECONDS = float(os.environ.get("BATCH_MAX_WAIT_SECONDS", 2 * 60 * 60))

# ---------------------------------------------------------------------------
# Batch API -- AWS Bedrock (see refcheck/llm/batch/bedrock_batch.py)
# ---------------------------------------------------------------------------
# Bedrock's batch inference API is fundamentally S3-based (unlike
# Anthropic's direct Batch API, which takes requests inline): you upload
# a JSONL file of requests to S3, kick off a CreateModelInvocationJob,
# and it writes results back to a different S3 location when done. All
# of this configuration is required to use bedrock_batch.py.
BEDROCK_BATCH_S3_BUCKET = os.environ.get("BEDROCK_BATCH_S3_BUCKET", "")
BEDROCK_BATCH_S3_INPUT_PREFIX = os.environ.get("BEDROCK_BATCH_S3_INPUT_PREFIX", "refcheck-batch/input")
BEDROCK_BATCH_S3_OUTPUT_PREFIX = os.environ.get("BEDROCK_BATCH_S3_OUTPUT_PREFIX", "refcheck-batch/output")
# IAM role ARN the Bedrock batch job assumes to read/write the S3
# locations above -- must trust bedrock.amazonaws.com and have
# read access to the input prefix + write access to the output prefix.
BEDROCK_BATCH_ROLE_ARN = os.environ.get("BEDROCK_BATCH_ROLE_ARN", "")
BEDROCK_BATCH_JOB_NAME_PREFIX = os.environ.get("BEDROCK_BATCH_JOB_NAME_PREFIX", "refcheck-batch")
BEDROCK_BATCH_POLL_INTERVAL_SECONDS = float(os.environ.get("BEDROCK_BATCH_POLL_INTERVAL_SECONDS", 30))
BEDROCK_BATCH_MAX_WAIT_SECONDS = float(os.environ.get("BEDROCK_BATCH_MAX_WAIT_SECONDS", 4 * 60 * 60))
