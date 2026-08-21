"""
Unit tests for ReferenceCheckNodes.evaluate_yes_no_form and has_comments
(the REF2 flow's pure-Python logic). No LLM calls.

Run with: pytest tests/test_yes_no_flow.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from refcheck.nodes.reference_nodes import ReferenceCheckNodes
from refcheck.schemas import ClaimedDetails, YesNoReferenceForm

nodes = ReferenceCheckNodes(llm_provider=None)


def make_claimed(**overrides) -> ClaimedDetails:
    defaults = dict(job_title="Support Specialist", company="Nimbus Cloud Services",
                     start_date="2022-03", end_date="2024-05")
    defaults.update(overrides)
    return ClaimedDetails(**defaults)


def make_form(**overrides) -> YesNoReferenceForm:
    defaults = dict(confirmed_title="yes", confirmed_dates="yes", confirmed_company="yes",
                     would_rehire="yes", performance_concerns="no", additional_comments=None)
    defaults.update(overrides)
    return YesNoReferenceForm(**defaults)


def test_all_confirmed_no_concerns_produces_no_discrepancies_or_flags():
    state = {"claimed_details": make_claimed(), "yes_no_form": make_form()}
    result = nodes.evaluate_yes_no_form(state)
    assert result["discrepancies"] == []
    assert result["red_flags"] == []
    assert result["sentiment"] == "neutral"


def test_no_confirmed_title_is_major_discrepancy():
    state = {"claimed_details": make_claimed(), "yes_no_form": make_form(confirmed_title="no")}
    result = nodes.evaluate_yes_no_form(state)
    title_flags = [d for d in result["discrepancies"] if d.field == "job_title"]
    assert len(title_flags) == 1
    assert title_flags[0].severity == "major"


def test_unsure_confirmed_dates_is_minor_discrepancy():
    state = {"claimed_details": make_claimed(), "yes_no_form": make_form(confirmed_dates="unsure")}
    result = nodes.evaluate_yes_no_form(state)
    date_flags = [d for d in result["discrepancies"] if d.field == "employment_dates"]
    assert len(date_flags) == 1
    assert date_flags[0].severity == "minor"


def test_performance_concerns_yes_adds_red_flag():
    state = {"claimed_details": make_claimed(), "yes_no_form": make_form(performance_concerns="yes")}
    result = nodes.evaluate_yes_no_form(state)
    assert any("performance concerns" in rf.lower() for rf in result["red_flags"])


def test_would_not_rehire_adds_red_flag():
    state = {"claimed_details": make_claimed(), "yes_no_form": make_form(would_rehire="no")}
    result = nodes.evaluate_yes_no_form(state)
    assert any("would not rehire" in rf.lower() for rf in result["red_flags"])


def test_has_comments_routes_to_sentiment_when_present():
    state = {"yes_no_form": make_form(additional_comments="Some notes here.")}
    assert nodes.has_comments(state) == "sentiment_from_comments"


def test_has_comments_routes_to_score_when_absent():
    state = {"yes_no_form": make_form(additional_comments=None)}
    assert nodes.has_comments(state) == "score_confidence"


def test_has_comments_routes_to_score_when_blank():
    state = {"yes_no_form": make_form(additional_comments="   ")}
    assert nodes.has_comments(state) == "score_confidence"


def test_evaluate_yes_no_form_feeds_into_shared_score_confidence():
    state = {"claimed_details": make_claimed(),
             "yes_no_form": make_form(confirmed_title="no", performance_concerns="yes")}
    eval_result = nodes.evaluate_yes_no_form(state)
    score_result = nodes.score_confidence(eval_result)
    assert score_result["needs_human_review"] is True
