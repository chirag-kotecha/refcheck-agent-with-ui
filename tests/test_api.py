"""
Unit tests for the FastAPI route handlers in refcheck/api/main.py.
Calls the handler functions directly (not over HTTP) and monkeypatches
run_check so no LLM call happens -- these test request validation and
store wiring, not the pipeline itself (that's covered elsewhere).

Run with: pytest tests/test_api.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import BackgroundTasks, HTTPException

from refcheck.api import main as api_main
from refcheck.api.schemas import CandidateCheckRequest
from refcheck.api.store import store
from refcheck.schemas import ClaimedDetails, ReferenceInput, YesNoReferenceForm


def make_request(references=None) -> CandidateCheckRequest:
    return CandidateCheckRequest(
        candidate_name="Test Candidate",
        role_applied_for="Engineer",
        claimed_details=ClaimedDetails(job_title="Engineer", company="Acme Corp", start_date="2021-01"),
        references=references if references is not None else [
            ReferenceInput(
                reference_name="Ref One", relationship="Manager", type="REF1",
                raw_input="This is a sufficiently long transcript text for validation to pass.",
            )
        ],
    )


def test_submit_check_rejects_empty_references():
    request = make_request(references=[])
    with pytest.raises(HTTPException) as exc_info:
        api_main.submit_check(request, BackgroundTasks())
    assert exc_info.value.status_code == 400


def test_submit_check_rejects_ref1_missing_raw_input():
    bad_ref = ReferenceInput(reference_name="Ref", relationship="Manager", type="REF1")
    request = make_request(references=[bad_ref])
    with pytest.raises(HTTPException) as exc_info:
        api_main.submit_check(request, BackgroundTasks())
    assert exc_info.value.status_code == 400


def test_submit_check_rejects_ref2_missing_form():
    bad_ref = ReferenceInput(reference_name="Ref", relationship="Manager", type="REF2")
    request = make_request(references=[bad_ref])
    with pytest.raises(HTTPException) as exc_info:
        api_main.submit_check(request, BackgroundTasks())
    assert exc_info.value.status_code == 400


def test_submit_check_valid_request_creates_queued_record(monkeypatch):
    # Prevent the real pipeline (which needs LLM credentials) from
    # running -- we're testing the endpoint/store wiring here, not the
    # pipeline itself.
    monkeypatch.setattr(api_main, "run_check", lambda *a, **k: None)

    request = make_request()
    response = api_main.submit_check(request, BackgroundTasks())

    assert response.status == "queued"
    record = store.get(response.check_id)
    assert record is not None
    assert record.status.value == "queued"


def test_submit_check_accepts_ref2_valid_form(monkeypatch):
    monkeypatch.setattr(api_main, "run_check", lambda *a, **k: None)

    ref2 = ReferenceInput(
        reference_name="HR Dept", relationship="Employer", type="REF2",
        yes_no_form=YesNoReferenceForm(
            confirmed_title="yes", confirmed_dates="yes", confirmed_company="yes",
            would_rehire="yes", performance_concerns="no",
        ),
    )
    request = make_request(references=[ref2])
    response = api_main.submit_check(request, BackgroundTasks())
    assert response.status == "queued"


def test_get_check_unknown_id_raises_404():
    with pytest.raises(HTTPException) as exc_info:
        api_main.get_check("definitely-not-a-real-id")
    assert exc_info.value.status_code == 404


def test_get_check_returns_current_status(monkeypatch):
    monkeypatch.setattr(api_main, "run_check", lambda *a, **k: None)
    request = make_request()
    submitted = api_main.submit_check(request, BackgroundTasks())

    status_response = api_main.get_check(submitted.check_id)
    assert status_response.check_id == submitted.check_id
    assert status_response.status == "queued"
    assert status_response.result is None


def test_get_schema_returns_expected_keys():
    schema = api_main.get_schema()
    assert set(schema.keys()) == {"claimed_details", "reference_input", "yes_no_reference_form"}
    assert "properties" in schema["reference_input"]
