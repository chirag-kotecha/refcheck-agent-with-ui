"""
Pydantic models + graph state definitions for both reference input types
and the candidate-level aggregation layer.
"""

import operator
from typing import Annotated, Literal, Optional, TypedDict
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Reference type codes. Named constants rather than scattering the raw
# strings "REF1"/"REF2" through graph-routing code -- see
# refcheck.graphs.candidate_graph.fan_out_references and
# refcheck.nodes.candidate_nodes.CandidateNodes.run_reference for where
# these drive dispatch.
# ---------------------------------------------------------------------------
REF_TYPE_OPEN_TEXT = "REF1"  # open-ended transcript/email
REF_TYPE_YES_NO = "REF2"     # structured yes/no verification form

ReferenceType = Literal["REF1", "REF2"]


# ---------------------------------------------------------------------------
# Input-side data (what the candidate claimed)
# ---------------------------------------------------------------------------

class ClaimedDetails(BaseModel):
    job_title: str
    company: str
    start_date: str  # normalized to YYYY-MM
    end_date: Optional[str] = None  # None => still employed there
    responsibilities: list[str] = Field(default_factory=list)
    reason_for_leaving: Optional[str] = None


# ---------------------------------------------------------------------------
# LLM output: facts extracted from a REF1 (open-text) transcript/email
# ---------------------------------------------------------------------------

class ExtractedFacts(BaseModel):
    job_title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    would_rehire: Optional[bool] = None
    performance_rating: Optional[Literal["strong", "average", "weak", "unclear"]] = None
    responsibilities_mentioned: list[str] = Field(default_factory=list)
    reason_for_leaving_mentioned: Optional[str] = None
    notable_quotes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# REF2 (yes/no) reference form -- the answers ARE the extracted facts,
# so there's no LLM extraction step for this type. See
# refcheck.nodes.reference_nodes.ReferenceCheckNodes.evaluate_yes_no_form.
# ---------------------------------------------------------------------------

YesNoAnswer = Literal["yes", "no", "unsure"]


class YesNoReferenceForm(BaseModel):
    confirmed_title: YesNoAnswer
    confirmed_dates: YesNoAnswer
    confirmed_company: YesNoAnswer
    would_rehire: YesNoAnswer
    performance_concerns: YesNoAnswer
    additional_comments: Optional[str] = None


# ---------------------------------------------------------------------------
# Programmatic diff output (built in Python, not by the LLM)
# ---------------------------------------------------------------------------

class Discrepancy(BaseModel):
    field: str
    claimed_value: str
    stated_value: str
    severity: Literal["minor", "moderate", "major"]
    note: Optional[str] = None


class DiscrepancyNote(BaseModel):
    field: str
    note: str


class DiscrepancyNotes(BaseModel):
    notes: list[DiscrepancyNote]


class SentimentAndRedFlags(BaseModel):
    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    red_flags: list[str] = Field(default_factory=list)


class FinalSummary(BaseModel):
    summary: str


class OverallSummary(BaseModel):
    summary: str


# ---------------------------------------------------------------------------
# Single-reference graph state (shared by both the REF1 and REF2 graphs)
# ---------------------------------------------------------------------------

class ReferenceCheckState(TypedDict, total=False):
    candidate_name: str
    role_applied_for: str
    claimed_details: ClaimedDetails

    # Exactly one of these is populated, matching `type` on the
    # originating ReferenceInput.
    raw_input: Optional[str]
    yes_no_form: Optional[YesNoReferenceForm]

    extracted_facts: Optional[ExtractedFacts]
    discrepancies: list[Discrepancy]
    sentiment: Optional[str]
    red_flags: list[str]

    confidence_score: Optional[float]
    needs_human_review: bool
    final_summary: Optional[str]


# ---------------------------------------------------------------------------
# Multi-reference layer
# ---------------------------------------------------------------------------

class ReferenceInput(BaseModel):
    """One reference to be checked.

    `type` selects the input shape:
      - REF_TYPE_OPEN_TEXT ("REF1"): a transcript/email -- populate `raw_input`.
      - REF_TYPE_YES_NO ("REF2"): a structured verification form --
        populate `yes_no_form`. `raw_input` is ignored for this type.
    """
    reference_name: str
    relationship: str  # e.g. "Former Manager", "Peer", "Direct Report"
    type: ReferenceType = REF_TYPE_OPEN_TEXT
    raw_input: Optional[str] = None
    yes_no_form: Optional[YesNoReferenceForm] = None

    def validate_shape(self) -> None:
        """Not a pydantic validator by design -- see validation.py's
        module docstring for why input-shape checks live separately.
        Call this explicitly wherever a ReferenceInput first enters the
        pipeline (candidate_nodes.run_reference / batch_runner phase 0)."""
        if self.type == REF_TYPE_OPEN_TEXT and not self.raw_input:
            raise ValueError(
                f"type={REF_TYPE_OPEN_TEXT!r} requires raw_input "
                f"(reference: {self.reference_name!r})"
            )
        if self.type == REF_TYPE_YES_NO and not self.yes_no_form:
            raise ValueError(
                f"type={REF_TYPE_YES_NO!r} requires yes_no_form "
                f"(reference: {self.reference_name!r})"
            )


class ReferenceResult(BaseModel):
    """Output of running the appropriate single-reference subgraph for
    one reference, packaged with identity info for the aggregator."""
    reference_name: str
    relationship: str
    extracted_facts: ExtractedFacts
    discrepancies: list[Discrepancy]
    sentiment: str
    red_flags: list[str]
    confidence_score: float
    needs_human_review: bool
    reference_summary: str


class CrossReferenceFlag(BaseModel):
    field: str
    description: str
    severity: Literal["minor", "moderate", "major"]
    involved_references: list[str]


class CandidateState(TypedDict, total=False):
    candidate_name: str
    role_applied_for: str
    claimed_details: ClaimedDetails
    references: list[ReferenceInput]

    reference_results: Annotated[list[ReferenceResult], operator.add]
    cross_reference_flags: list[CrossReferenceFlag]
    overall_confidence: Optional[float]
    overall_needs_review: bool
    overall_summary: Optional[str]
