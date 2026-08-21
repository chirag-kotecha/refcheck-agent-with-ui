"""
Unit tests for pure-Python logic in CandidateNodes -- cross_check_references,
score_overall, route_overall_review. No LLM calls.

Run with: pytest tests/test_candidate_nodes.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from refcheck.nodes.candidate_nodes import CandidateNodes
from refcheck.schemas import CrossReferenceFlag, ExtractedFacts, ReferenceResult

candidate_nodes = CandidateNodes(llm_provider=None)


def make_result(**overrides) -> ReferenceResult:
    defaults = dict(
        reference_name="Ref A", relationship="Former Manager",
        extracted_facts=ExtractedFacts(job_title="Analyst", company="Acme Corp", performance_rating="strong"),
        discrepancies=[], sentiment="positive", red_flags=[],
        confidence_score=90.0, needs_human_review=False, reference_summary="Clean reference.",
    )
    defaults.update(overrides)
    return ReferenceResult(**defaults)


def test_cross_check_no_flags_when_references_agree():
    state = {"reference_results": [make_result(reference_name="Ref A"), make_result(reference_name="Ref B")]}
    assert candidate_nodes.cross_check_references(state)["cross_reference_flags"] == []


def test_cross_check_flags_company_disagreement_as_major():
    state = {"reference_results": [
        make_result(reference_name="Ref A", extracted_facts=ExtractedFacts(company="Acme Corp")),
        make_result(reference_name="Ref B", extracted_facts=ExtractedFacts(company="Globex Inc")),
    ]}
    result = candidate_nodes.cross_check_references(state)
    company_flags = [f for f in result["cross_reference_flags"] if f.field == "company"]
    assert len(company_flags) == 1
    assert company_flags[0].severity == "major"
    assert set(company_flags[0].involved_references) == {"Ref A", "Ref B"}


def test_cross_check_flags_title_disagreement_as_moderate():
    state = {"reference_results": [
        make_result(reference_name="Ref A", extracted_facts=ExtractedFacts(job_title="Manager")),
        make_result(reference_name="Ref B", extracted_facts=ExtractedFacts(job_title="Associate")),
    ]}
    result = candidate_nodes.cross_check_references(state)
    title_flags = [f for f in result["cross_reference_flags"] if f.field == "job_title"]
    assert len(title_flags) == 1
    assert title_flags[0].severity == "moderate"


def test_cross_check_flags_conflicting_performance_ratings():
    state = {"reference_results": [
        make_result(reference_name="Ref A", extracted_facts=ExtractedFacts(performance_rating="strong")),
        make_result(reference_name="Ref B", extracted_facts=ExtractedFacts(performance_rating="weak")),
    ]}
    result = candidate_nodes.cross_check_references(state)
    perf_flags = [f for f in result["cross_reference_flags"] if f.field == "performance_rating"]
    assert len(perf_flags) == 1
    assert perf_flags[0].severity == "major"


def test_cross_check_ignores_fields_only_one_reference_mentioned():
    state = {"reference_results": [
        make_result(reference_name="Ref A", extracted_facts=ExtractedFacts(company="Acme Corp")),
        make_result(reference_name="Ref B", extracted_facts=ExtractedFacts(company=None)),
    ]}
    assert candidate_nodes.cross_check_references(state)["cross_reference_flags"] == []


def test_score_overall_averages_reference_scores():
    state = {
        "reference_results": [
            make_result(confidence_score=100.0, needs_human_review=False),
            make_result(confidence_score=80.0, needs_human_review=False),
        ],
        "cross_reference_flags": [],
    }
    result = candidate_nodes.score_overall(state)
    assert result["overall_confidence"] == 90.0
    assert result["overall_needs_review"] is False


def test_score_overall_penalizes_cross_reference_flags():
    state = {
        "reference_results": [
            make_result(confidence_score=100.0, needs_human_review=False),
            make_result(confidence_score=100.0, needs_human_review=False),
        ],
        "cross_reference_flags": [
            CrossReferenceFlag(field="company", description="mismatch", severity="major",
                                involved_references=["Ref A", "Ref B"]),
        ],
    }
    result = candidate_nodes.score_overall(state)
    assert result["overall_confidence"] == 65.0
    assert result["overall_needs_review"] is True


def test_score_overall_any_reference_needing_review_forces_overall_review():
    state = {
        "reference_results": [
            make_result(confidence_score=100.0, needs_human_review=True),
            make_result(confidence_score=100.0, needs_human_review=False),
        ],
        "cross_reference_flags": [],
    }
    assert candidate_nodes.score_overall(state)["overall_needs_review"] is True


def test_route_overall_review_flags_when_needed():
    assert candidate_nodes.route_overall_review({"overall_needs_review": True}) == "overall_flag_for_review"


def test_route_overall_review_clears_when_not_needed():
    assert candidate_nodes.route_overall_review({"overall_needs_review": False}) == "overall_clear"
