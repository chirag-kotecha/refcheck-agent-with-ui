"""
Executes a candidate reference check in the background and updates the
job store. Uses the exact same candidate_graph as run_demo_multi.py --
no separate business logic for the API path, just an async wrapper
around it.

The compiled graph (and the provider it holds) is built lazily on first
use and cached, rather than at module import time -- so simply
`import refcheck.api.main` (e.g. for tests, or FastAPI's OpenAPI schema
generation) doesn't require LLM credentials to succeed. Call
`warm_up()` from a startup hook if you want the first real request to
not pay the graph-build cost.
"""

from typing import Optional

from refcheck import config
from refcheck.graphs.candidate_graph import build_candidate_graph
from refcheck.llm.providers import get_provider
from refcheck.logging_config import get_logger
from refcheck.api.store import store
from refcheck.api.schemas import CandidateCheckRequest

logger = get_logger(__name__)

_candidate_app = None


def warm_up() -> None:
    """Builds and caches the candidate graph. Optional -- called from
    main.py's startup event so the first HTTP request isn't slower than
    the rest; also safe to call multiple times (no-op after the first)."""
    global _candidate_app
    if _candidate_app is None:
        provider = get_provider()
        _candidate_app = build_candidate_graph(provider)
        logger.info(f"candidate graph built, provider={provider.PROVIDER_NAME}")


def _get_app():
    warm_up()
    return _candidate_app


def _to_json(value):
    """Recursively converts a CandidateState-shaped result (with
    Pydantic model fields inside) into a plain JSON-serializable value."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_json(v) for k, v in value.items()}
    return value


def run_check(check_id: str, request: CandidateCheckRequest) -> None:
    """Runs one candidate check end-to-end and records the outcome.
    Intended to be scheduled via FastAPI's BackgroundTasks -- see
    main.py:submit_check -- so it executes after the 202 response for
    the submitting request has already been sent."""
    store.mark_running(check_id)
    try:
        input_state = {
            "candidate_name": request.candidate_name,
            "role_applied_for": request.role_applied_for,
            "claimed_details": request.claimed_details,
            "references": request.references,
        }
        app = _get_app()
        result = app.invoke(
            input_state, config={"max_concurrency": config.MAX_CONCURRENT_REFERENCES}
        )
        store.mark_completed(check_id, _to_json(result))
        logger.info(f"check completed: check_id={check_id}")
    except Exception as e:
        logger.error(f"check failed: check_id={check_id} error={e!r}")
        store.mark_failed(check_id, str(e))

    record = store.get(check_id)
    if record and record.callback_url:
        _send_callback(record)


def _send_callback(record) -> None:
    """Best-effort webhook delivery -- logs and swallows failures rather
    than raising, since a bad callback_url shouldn't make the check
    itself look failed (the result is still available via polling)."""
    try:
        import httpx
        payload = {
            "check_id": record.check_id,
            "status": record.status,
            "result": record.result,
            "error": record.error,
        }
        httpx.post(record.callback_url, json=payload, timeout=10)
        logger.info(f"callback delivered: check_id={record.check_id} url={record.callback_url}")
    except Exception as e:
        logger.error(f"callback delivery failed: check_id={record.check_id} error={e!r}")
