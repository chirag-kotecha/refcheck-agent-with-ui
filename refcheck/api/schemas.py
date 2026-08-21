"""
API request/response models. Reuses refcheck.schemas' ClaimedDetails and
ReferenceInput directly as the request body shape for candidate/reference
fields -- FastAPI validates these natively -- so there's exactly one
definition of what a reference/candidate looks like, shared between the
real-time graph, the batch pipeline, and this API.
"""

from typing import Optional

from pydantic import BaseModel, Field

from refcheck.schemas import ClaimedDetails, ReferenceInput


class CandidateCheckRequest(BaseModel):
    candidate_name: str
    role_applied_for: str
    claimed_details: ClaimedDetails
    references: list[ReferenceInput]
    callback_url: Optional[str] = Field(
        default=None,
        description=(
            "If provided, the full result is POSTed here as JSON once the "
            "check completes (fire-and-forget, logged on failure, not "
            "retried). The check is always pollable via GET regardless of "
            "whether this is set."
        ),
    )


class CheckSubmittedResponse(BaseModel):
    check_id: str
    status: str


class CheckStatusResponse(BaseModel):
    check_id: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None
