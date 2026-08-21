"""
Unit tests for pure-Python logic in ReferenceCheckNodes -- diff_facts,
score_confidence, _month_diff, and routing functions. No LLM calls.

Run with: pytest tests/test_nodes.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from refcheck.nodes.reference_nodes import ReferenceCheckNodes
from refcheck.schemas import ClaimedDetails, Discrepancy, ExtractedFacts

nodes = ReferenceCheckNodes(llm_provider=None)


def make_claimed(**overrides) -> ClaimedDetails:
    defaults = dict(
        job_title="Product Manager", company="Acme Corp",
        start_date="2021-01", end_date="2023-06",
        responsibilities=["roadmap"], reason_for_leaving="growth",
    )
    defaults.update(overrides)
    return ClaimedDetails(**defaults)


def make_facts(**overrides) -> ExtractedFacts:
    defaults = dict(job_title="Product Manager", company="Acme Corp",
                     start_date="2021-01", end_date="2023-06")
    defaults.update(overrides)
    return ExtractedFacts(**defaults)


def test_month_diff_same_month():
    assert nodes._month_diff("2021-01", "2021-01") == 0


def test_month_diff_across_years():
    assert nodes._month_diff("2021-01", "2023-06") == 29


def test_month_diff_invalid_input_returns_none():
    assert nodes._month_diff("not-a-date", "2021-01") is None
    assert nodes._month_diff(None, "2021-01") is None


def test_diff_facts_no_discrepancies_when_everything_matches():
    state = {"claimed_details": make_claimed(), "extracted_facts": make_facts()}
    assert nodes.diff_facts(state)["discrepancies"] == []


def test_diff_facts_flags_company_mismatch_as_major():
    state = {"claimed_details": make_claimed(company="Acme Corp"),
             "extracted_facts": make_facts(company="Globex Inc")}
    result = nodes.diff_facts(state)
    company_flags = [d for d in result["discrepancies"] if d.field == "company"]
    assert len(company_flags) == 1
    assert company_flags[0].severity == "major"


def test_diff_facts_seniority_downgrade_is_major():
    state = {"claimed_details": make_claimed(job_title="Senior Manager"),
             "extracted_facts": make_facts(job_title="Associate")}
    result = nodes.diff_facts(state)
    title_flags = [d for d in result["discrepancies"] if d.field == "job_title"]
    assert len(title_flags) == 1
    assert title_flags[0].severity == "major"


def test_diff_facts_lateral_title_change_is_moderate():
    state = {"claimed_details": make_claimed(job_title="Product Manager"),
             "extracted_facts": make_facts(job_title="Program Manager")}
    result = nodes.diff_facts(state)
    title_flags = [d for d in result["discrepancies"] if d.field == "job_title"]
    assert len(title_flags) == 1
    assert title_flags[0].severity == "moderate"


def test_diff_facts_small_date_gap_within_tolerance_not_flagged():
    state = {"claimed_details": make_claimed(start_date="2021-01"),
             "extracted_facts": make_facts(start_date="2021-02")}
    result = nodes.diff_facts(state)
    assert [d for d in result["discrepancies"] if d.field == "start_date"] == []


def test_diff_facts_large_date_gap_is_major():
    state = {"claimed_details": make_claimed(start_date="2021-01"),
             "extracted_facts": make_facts(start_date="2022-06")}
    result = nodes.diff_facts(state)
    date_flags = [d for d in result["discrepancies"] if d.field == "start_date"]
    assert len(date_flags) == 1
    assert date_flags[0].severity == "major"


def test_diff_facts_moderate_date_gap():
    state = {"claimed_details": make_claimed(start_date="2021-01"),
             "extracted_facts": make_facts(start_date="2021-04")}
    result = nodes.diff_facts(state)
    date_flags = [d for d in result["discrepancies"] if d.field == "start_date"]
    assert len(date_flags) == 1
    assert date_flags[0].severity == "moderate"


def test_diff_facts_reference_claims_end_date_candidate_says_current():
    state = {"claimed_details": make_claimed(end_date=None),
             "extracted_facts": make_facts(end_date="2023-01")}
    result = nodes.diff_facts(state)
    end_flags = [d for d in result["discrepancies"] if d.field == "end_date"]
    assert len(end_flags) == 1
    assert end_flags[0].severity == "major"


def test_diff_facts_null_extracted_fields_are_not_discrepancies():
    state = {"claimed_details": make_claimed(),
             "extracted_facts": make_facts(job_title=None, company=None, start_date=None, end_date=None)}
    assert nodes.diff_facts(state)["discrepancies"] == []


def test_has_discrepancies_routes_to_explain_when_present():
    state = {"discrepancies": [Discrepancy(field="company", claimed_value="A", stated_value="B", severity="major")]}
    assert nodes.has_discrepancies(state) == "explain_discrepancies"


def test_has_discrepancies_routes_to_score_when_empty():
    assert nodes.has_discrepancies({"discrepancies": []}) == "score_confidence"


def test_score_confidence_perfect_case():
    state = {"discrepancies": [], "red_flags": [], "sentiment": "positive"}
    result = nodes.score_confidence(state)
    assert result["confidence_score"] == 100.0
    assert result["needs_human_review"] is False


def test_score_confidence_major_discrepancy_forces_review():
    state = {"discrepancies": [Discrepancy(field="company", claimed_value="A", stated_value="B", severity="major")],
             "red_flags": [], "sentiment": "positive"}
    assert nodes.score_confidence(state)["needs_human_review"] is True


def test_score_confidence_red_flags_force_review():
    state = {"discrepancies": [], "red_flags": ["evasive about rehire"], "sentiment": "neutral"}
    assert nodes.score_confidence(state)["needs_human_review"] is True


def test_score_confidence_never_goes_below_zero():
    many_majors = [Discrepancy(field=f"f{i}", claimed_value="a", stated_value="b", severity="major") for i in range(10)]
    state = {"discrepancies": many_majors, "red_flags": [], "sentiment": "negative"}
    assert nodes.score_confidence(state)["confidence_score"] == 0.0


def test_score_confidence_minor_discrepancy_alone_may_not_force_review():
    state = {"discrepancies": [Discrepancy(field="job_title", claimed_value="A", stated_value="A2", severity="minor")],
             "red_flags": [], "sentiment": "positive"}
    result = nodes.score_confidence(state)
    assert result["confidence_score"] == 95.0
    assert result["needs_human_review"] is False


def test_route_review_flags_when_needed():
    assert nodes.route_review({"needs_human_review": True}) == "flag_for_human_review"


def test_route_review_clears_when_not_needed():
    assert nodes.route_review({"needs_human_review": False}) == "auto_summarize"
