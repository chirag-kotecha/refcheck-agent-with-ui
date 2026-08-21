"""
Unit tests for ReferenceInput.validate_shape() and the REF1/REF2 type
constants. No LLM calls.

Run with: pytest tests/test_schemas.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from refcheck.schemas import REF_TYPE_OPEN_TEXT, REF_TYPE_YES_NO, ReferenceInput, YesNoReferenceForm


def test_ref_type_constants_match_expected_codes():
    assert REF_TYPE_OPEN_TEXT == "REF1"
    assert REF_TYPE_YES_NO == "REF2"


def test_ref1_with_raw_input_validates_ok():
    ref = ReferenceInput(reference_name="Jane", relationship="Manager",
                          type="REF1", raw_input="Some transcript text here.")
    ref.validate_shape()  # should not raise


def test_ref1_without_raw_input_raises():
    ref = ReferenceInput(reference_name="Jane", relationship="Manager", type="REF1")
    with pytest.raises(ValueError):
        ref.validate_shape()


def test_ref2_with_form_validates_ok():
    ref = ReferenceInput(
        reference_name="HR Dept", relationship="Employer", type="REF2",
        yes_no_form=YesNoReferenceForm(
            confirmed_title="yes", confirmed_dates="yes", confirmed_company="yes",
            would_rehire="yes", performance_concerns="no",
        ),
    )
    ref.validate_shape()  # should not raise


def test_ref2_without_form_raises():
    ref = ReferenceInput(reference_name="HR Dept", relationship="Employer", type="REF2")
    with pytest.raises(ValueError):
        ref.validate_shape()


def test_default_type_is_ref1():
    ref = ReferenceInput(reference_name="Jane", relationship="Manager", raw_input="Some text.")
    assert ref.type == REF_TYPE_OPEN_TEXT
