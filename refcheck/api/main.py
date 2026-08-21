"""
FastAPI service exposing the reference-check pipeline over HTTP.

    POST /api/v1/checks        submit a candidate check, returns check_id immediately (202)
    GET  /api/v1/checks/{id}   poll status / retrieve result
    GET  /api/v1/schema        JSON schema for the request shapes (for building a dynamic UI)
    GET  /health                liveness check

Submission is async: the endpoint returns as soon as the check is
queued, the actual graph run happens in a FastAPI BackgroundTask (see
runner.py), and the caller either polls GET /api/v1/checks/{id} or
supplies a callback_url to receive the result via webhook when it's
done -- both work regardless of which one you use.

Run with:
    uvicorn refcheck.api.main:app --reload --port 8000
or via Docker (see docker-compose.yml's `api` service).
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException

from refcheck.api.schemas import CandidateCheckRequest, CheckSubmittedResponse, CheckStatusResponse
from refcheck.api.store import store
from refcheck.api.runner import run_check, warm_up
from refcheck.schemas import ClaimedDetails, ReferenceInput, YesNoReferenceForm

app = FastAPI(
    title="Reference Check Analyzer API",
    description=(
        "Submit candidate reference checks (REF1 open-text transcripts/"
        "emails, or REF2 structured yes/no verification forms, or a mix) "
        "and poll for results, or supply a callback_url to be notified "
        "when a check completes."
    ),
    version="1.0.0",
)


@app.on_event("startup")
def _startup():
    # Builds the graph once at process startup rather than on the first
    # request, so request latency is consistent from the first call.
    warm_up()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/checks", response_model=CheckSubmittedResponse, status_code=202)
def submit_check(request: CandidateCheckRequest, background_tasks: BackgroundTasks):
    if not request.references:
        raise HTTPException(status_code=400, detail="At least one reference is required.")

    for ref in request.references:
        try:
            ref.validate_shape()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    record = store.create(callback_url=request.callback_url)
    background_tasks.add_task(run_check, record.check_id, request)
    return CheckSubmittedResponse(check_id=record.check_id, status=record.status.value)


@app.get("/api/v1/checks/{check_id}", response_model=CheckStatusResponse)
def get_check(check_id: str):
    record = store.get(check_id)
    if record is None:
        raise HTTPException(status_code=404, detail="check_id not found")
    return CheckStatusResponse(
        check_id=record.check_id,
        status=record.status.value,
        result=record.result,
        error=record.error,
    )


@app.get("/api/v1/schema")
def get_schema():
    """Returns JSON schema for the request body shapes -- lets a client
    (e.g. streamlit_app.py) discover REF1 vs REF2 field requirements
    without hardcoding them, though the bundled Streamlit UI hardcodes
    them for simplicity since it ships alongside this API."""
    return {
        "claimed_details": ClaimedDetails.model_json_schema(),
        "reference_input": ReferenceInput.model_json_schema(),
        "yes_no_reference_form": YesNoReferenceForm.model_json_schema(),
    }
