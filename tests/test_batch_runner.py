"""
Unit tests for the parts of batch_runner.py that don't call a Batch API
-- the custom_id convention and reuse of ReferenceCheckNodes /
CandidateNodes pure functions on batch-shaped state dicts.

Run with: pytest tests/test_batch_runner.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from refcheck.pipelines import batch_runner as br
from refcheck.nodes.reference_nodes import ReferenceCheckNodes
from refcheck.schemas import ClaimedDetails, ExtractedFacts

nodes = ReferenceCheckNodes(llm_provider=None)


def test_cid_is_unique_per_reference_and_tag():
    ids = {
        br._cid(0, 0, "extract"), br._cid(0, 0, "sentiment"),
        br._cid(0, 1, "extract"), br._cid(1, 0, "extract"),
    }
    assert len(ids) == 4


def test_cid_format_is_parseable():
    assert br._cid(3, 7, "explain") == "c3:r7:explain"


def test_parse_cid_round_trips():
    assert br._parse_cid(br._cid(5, 9, "summary")) == (5, 9)


def test_get_batch_backend_unknown_provider_raises():
    with pytest.raises(ValueError):
        br._get_batch_backend("not-a-real-provider")


def test_get_batch_backend_anthropic_resolves():
    backend = br._get_batch_backend("anthropic")
    assert hasattr(backend, "run_batch_sync")


def test_diff_facts_reused_correctly_on_batch_shaped_state():
    claimed = ClaimedDetails(job_title="Analyst", company="Acme Corp", start_date="2021-01", end_date="2023-01")
    facts = ExtractedFacts(job_title="Analyst", company="Globex Inc", start_date="2021-01")
    state = {"claimed_details": claimed, "extracted_facts": facts}

    result = nodes.diff_facts(state)
    company_flags = [d for d in result["discrepancies"] if d.field == "company"]
    assert len(company_flags) == 1
    assert company_flags[0].severity == "major"
