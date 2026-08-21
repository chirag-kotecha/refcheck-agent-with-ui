"""
Bulk/offline reference-check processing via a Batch API backend
(Anthropic direct or AWS Bedrock -- see `batch_provider` param).

Same relationship to the real-time graphs as before: not a mode switch,
a separate pipeline restructured into phases so every LLM call of the
same kind, across every candidate and reference in the input batch, is
submitted together as one batch job.

Handles BOTH reference types (REF1 open-text, REF2 yes/no form):

  1. (batch)  REF1: extract_facts + sentiment_and_redflags
              REF2: nothing (the form's answers ARE the facts)
  2. (python) REF1: diff_facts / REF2: evaluate_yes_no_form
  3. (batch)  REF2 only, conditional: sentiment_from_comments
  4. (batch)  REF1 only, conditional: explain_discrepancies
  5. (python) score_confidence + route_review, both types
  6. (batch)  flag_for_human_review OR auto_summarize, both types
  7. (python) cross_check_references + score_overall + routing, per candidate
  8. (batch)  overall_flag_for_review OR overall_clear, per candidate

`batch_provider` selects which batch backend handles every "(batch)"
phase above, AND which provider name is used for model-tier resolution
(config.get_model(batch_provider, tier)) -- exactly the same generic
tiering used by the real-time providers, just applied to whichever
batch backend is active:
  - "anthropic" (default): refcheck.llm.batch.anthropic_batch
  - "bedrock": refcheck.llm.batch.bedrock_batch (see that module's
    docstring for the S3/IAM setup it requires, and its "one job per
    model" constraint)

Deterministic logic is reused directly from ReferenceCheckNodes /
CandidateNodes instantiated with llm_provider=None.
"""

from dataclasses import dataclass

from refcheck import config
from refcheck.nodes.candidate_nodes import CandidateNodes
from refcheck.nodes.reference_nodes import ReferenceCheckNodes
from refcheck import request_builders as rb
from refcheck.llm.batch.base import BatchItem
from refcheck.logging_config import get_logger
from refcheck.validation import validate_raw_input, ValidationError
from refcheck.schemas import (
    ClaimedDetails,
    CrossReferenceFlag,
    Discrepancy,
    DiscrepancyNotes,
    ExtractedFacts,
    FinalSummary,
    OverallSummary,
    REF_TYPE_OPEN_TEXT,
    REF_TYPE_YES_NO,
    ReferenceInput,
    ReferenceResult,
    SentimentAndRedFlags,
)

logger = get_logger(__name__)

_reference_nodes = ReferenceCheckNodes(llm_provider=None)
_candidate_nodes = CandidateNodes(llm_provider=None)


def _get_batch_backend(batch_provider: str):
    if batch_provider == "anthropic":
        from refcheck.llm.batch import anthropic_batch as backend
    elif batch_provider == "bedrock":
        from refcheck.llm.batch import bedrock_batch as backend
    else:
        raise ValueError(f"Unknown batch_provider={batch_provider!r}. Expected 'anthropic' or 'bedrock'.")
    return backend


@dataclass
class CandidateBatchInput:
    candidate_name: str
    role_applied_for: str
    claimed_details: ClaimedDetails
    references: list[ReferenceInput]


def _cid(candidate_idx: int, ref_idx: int, tag: str) -> str:
    return f"c{candidate_idx}:r{ref_idx}:{tag}"


def _parse_cid(custom_id: str) -> tuple[int, int]:
    parts = custom_id.split(":")
    return int(parts[0][1:]), int(parts[1][1:])


def run_batch_pipeline(candidates: list[CandidateBatchInput], batch_provider: str = "anthropic") -> list[dict]:
    """
    Runs the full reference-check pipeline for every candidate via the
    selected batch backend. Returns a list of dicts shaped like
    CandidateState -- same shape candidate_graph.py produces.
    """
    backend = _get_batch_backend(batch_provider)
    model_extraction = config.get_model(batch_provider, "extraction")
    model_reasoning = config.get_model(batch_provider, "reasoning")

    n_candidates = len(candidates)
    n_references = sum(len(c.references) for c in candidates)
    logger.info(
        f"batch pipeline start: provider={batch_provider} candidates={n_candidates} "
        f"references={n_references}"
    )

    # -----------------------------------------------------------------
    # Phase 0: validate inputs up front.
    # -----------------------------------------------------------------
    invalid_refs: dict[tuple[int, int], str] = {}
    for c_idx, candidate in enumerate(candidates):
        for r_idx, ref in enumerate(candidate.references):
            try:
                ref.validate_shape()
                if ref.type == REF_TYPE_OPEN_TEXT:
                    validate_raw_input(
                        ref.raw_input, context=f"{candidate.candidate_name}/{ref.reference_name}"
                    )
            except (ValidationError, ValueError) as e:
                invalid_refs[(c_idx, r_idx)] = str(e)
                logger.error(f"validation failed, excluding from batch: {_cid(c_idx, r_idx, '')} error={e}")

    # -----------------------------------------------------------------
    # Phase 1: extract_facts + sentiment_and_redflags -- REF1 only.
    # -----------------------------------------------------------------
    phase1_items = []
    for c_idx, candidate in enumerate(candidates):
        for r_idx, ref in enumerate(candidate.references):
            if (c_idx, r_idx) in invalid_refs or ref.type != REF_TYPE_OPEN_TEXT:
                continue
            system, user_message = rb.extract_facts_request(
                candidate.candidate_name, candidate.role_applied_for,
                candidate.claimed_details, ref.raw_input,
            )
            phase1_items.append(BatchItem(
                custom_id=_cid(c_idx, r_idx, "extract"),
                system=system, user_message=user_message,
                output_model=ExtractedFacts, model=model_extraction,
            ))
            system, user_message = rb.sentiment_and_redflags_request(ref.raw_input)
            phase1_items.append(BatchItem(
                custom_id=_cid(c_idx, r_idx, "sentiment"),
                system=system, user_message=user_message,
                output_model=SentimentAndRedFlags, model=model_extraction,
            ))

    phase1_results = backend.run_batch_sync(phase1_items) if phase1_items else {}
    logger.info(f"phase 1 (extract+sentiment, REF1) done: {len(phase1_items)} requests")

    # -----------------------------------------------------------------
    # Phase 2: diff_facts (REF1) / evaluate_yes_no_form (REF2). Pure
    # Python, reused from ReferenceCheckNodes.
    # -----------------------------------------------------------------
    discrepancies_by_ref: dict[tuple[int, int], list[Discrepancy]] = {}
    extracted_by_ref: dict[tuple[int, int], ExtractedFacts] = {}
    sentiment_by_ref: dict[tuple[int, int], str] = {}
    red_flags_by_ref: dict[tuple[int, int], list[str]] = {}

    for c_idx, candidate in enumerate(candidates):
        for r_idx, ref in enumerate(candidate.references):
            if (c_idx, r_idx) in invalid_refs:
                continue
            key = (c_idx, r_idx)

            if ref.type == REF_TYPE_OPEN_TEXT:
                extract_result = phase1_results[_cid(c_idx, r_idx, "extract")]
                sentiment_result = phase1_results[_cid(c_idx, r_idx, "sentiment")]

                facts = extract_result.value if extract_result.success else ExtractedFacts()
                sentiment_obj = (
                    sentiment_result.value if sentiment_result.success
                    else SentimentAndRedFlags(sentiment="unclear", red_flags=[])
                )
                extracted_by_ref[key] = facts
                sentiment_by_ref[key] = sentiment_obj.sentiment
                red_flags_by_ref[key] = sentiment_obj.red_flags

                diff_state = {"claimed_details": candidate.claimed_details, "extracted_facts": facts}
                discrepancies_by_ref[key] = _reference_nodes.diff_facts(diff_state)["discrepancies"]

            else:  # REF2
                eval_state = {"claimed_details": candidate.claimed_details, "yes_no_form": ref.yes_no_form}
                eval_result = _reference_nodes.evaluate_yes_no_form(eval_state)
                extracted_by_ref[key] = ExtractedFacts()
                sentiment_by_ref[key] = eval_result["sentiment"]
                red_flags_by_ref[key] = eval_result["red_flags"]
                discrepancies_by_ref[key] = eval_result["discrepancies"]

    # -----------------------------------------------------------------
    # Phase 3: sentiment_from_comments -- REF2 only, if comments present.
    # -----------------------------------------------------------------
    phase3_items = []
    for c_idx, candidate in enumerate(candidates):
        for r_idx, ref in enumerate(candidate.references):
            key = (c_idx, r_idx)
            if key in invalid_refs or ref.type != REF_TYPE_YES_NO:
                continue
            comments = (ref.yes_no_form.additional_comments or "").strip()
            if not comments:
                continue
            system, user_message = rb.sentiment_and_redflags_request(comments)
            phase3_items.append(BatchItem(
                custom_id=_cid(c_idx, r_idx, "comment_sentiment"),
                system=system, user_message=user_message,
                output_model=SentimentAndRedFlags, model=model_extraction,
            ))

    phase3_results = backend.run_batch_sync(phase3_items) if phase3_items else {}
    logger.info(f"phase 3 (comment sentiment, REF2) done: {len(phase3_items)} requests")

    for item in phase3_items:
        result = phase3_results.get(item.custom_id)
        c_idx, r_idx = _parse_cid(item.custom_id)
        key = (c_idx, r_idx)
        if result and result.success:
            sentiment_by_ref[key] = result.value.sentiment
            red_flags_by_ref[key] = red_flags_by_ref[key] + result.value.red_flags

    # -----------------------------------------------------------------
    # Phase 4: explain_discrepancies -- REF1 only, only if any exist.
    # -----------------------------------------------------------------
    phase4_items = []
    for c_idx, candidate in enumerate(candidates):
        for r_idx, ref in enumerate(candidate.references):
            key = (c_idx, r_idx)
            if key in invalid_refs or ref.type != REF_TYPE_OPEN_TEXT:
                continue
            discrepancies = discrepancies_by_ref[key]
            if not discrepancies:
                continue
            system, user_message = rb.explain_discrepancies_request(discrepancies)
            phase4_items.append(BatchItem(
                custom_id=_cid(c_idx, r_idx, "explain"),
                system=system, user_message=user_message,
                output_model=DiscrepancyNotes, model=model_reasoning,
            ))

    phase4_results = backend.run_batch_sync(phase4_items) if phase4_items else {}
    logger.info(f"phase 4 (explain_discrepancies, REF1) done: {len(phase4_items)} requests")

    for item in phase4_items:
        result = phase4_results.get(item.custom_id)
        c_idx, r_idx = _parse_cid(item.custom_id)
        key = (c_idx, r_idx)
        if result and result.success:
            notes_by_field = {n.field: n.note for n in result.value.notes}
            discrepancies_by_ref[key] = [
                d.model_copy(update={"note": notes_by_field.get(d.field, d.note)})
                for d in discrepancies_by_ref[key]
            ]

    # -----------------------------------------------------------------
    # Phase 5: score_confidence + route_review (pure Python), both types.
    # -----------------------------------------------------------------
    confidence_by_ref: dict[tuple[int, int], float] = {}
    needs_review_by_ref: dict[tuple[int, int], bool] = {}
    route_by_ref: dict[tuple[int, int], str] = {}

    for c_idx, candidate in enumerate(candidates):
        for r_idx, ref in enumerate(candidate.references):
            key = (c_idx, r_idx)
            if key in invalid_refs:
                continue
            score_state = {
                "discrepancies": discrepancies_by_ref[key],
                "red_flags": red_flags_by_ref[key],
                "sentiment": sentiment_by_ref[key],
            }
            score_result = _reference_nodes.score_confidence(score_state)
            confidence_by_ref[key] = score_result["confidence_score"]
            needs_review_by_ref[key] = score_result["needs_human_review"]
            route_by_ref[key] = _reference_nodes.route_review(score_result)

    # -----------------------------------------------------------------
    # Phase 6: flag_for_human_review OR auto_summarize, both types.
    # -----------------------------------------------------------------
    phase6_items = []
    for c_idx, candidate in enumerate(candidates):
        for r_idx, ref in enumerate(candidate.references):
            key = (c_idx, r_idx)
            if key in invalid_refs:
                continue
            if route_by_ref[key] == "flag_for_human_review":
                system, user_message = rb.flag_for_human_review_request(
                    candidate.candidate_name, candidate.role_applied_for,
                    confidence_by_ref[key], sentiment_by_ref[key],
                    discrepancies_by_ref[key], red_flags_by_ref[key],
                )
            else:
                system, user_message = rb.auto_summarize_request(
                    candidate.candidate_name, candidate.role_applied_for,
                    confidence_by_ref[key], sentiment_by_ref[key],
                    candidate.claimed_details,
                )
            phase6_items.append(BatchItem(
                custom_id=_cid(c_idx, r_idx, "summary"),
                system=system, user_message=user_message,
                output_model=FinalSummary, model=model_reasoning,
            ))

    phase6_results = backend.run_batch_sync(phase6_items) if phase6_items else {}
    logger.info(f"phase 6 (reference summaries) done: {len(phase6_items)} requests")

    # -----------------------------------------------------------------
    # Assemble ReferenceResult per reference.
    # -----------------------------------------------------------------
    reference_results_by_candidate: dict[int, list[ReferenceResult]] = {
        c_idx: [] for c_idx in range(n_candidates)
    }

    for c_idx, candidate in enumerate(candidates):
        for r_idx, ref in enumerate(candidate.references):
            key = (c_idx, r_idx)
            if key in invalid_refs:
                reference_results_by_candidate[c_idx].append(ReferenceResult(
                    reference_name=ref.reference_name,
                    relationship=ref.relationship,
                    extracted_facts=ExtractedFacts(),
                    discrepancies=[],
                    sentiment="unclear",
                    red_flags=[f"Excluded from batch: {invalid_refs[key]}"],
                    confidence_score=0.0,
                    needs_human_review=True,
                    reference_summary="This reference failed input validation and was not processed. Manual review required.",
                ))
                continue

            summary_result = phase6_results.get(_cid(c_idx, r_idx, "summary"))
            summary_text = (
                summary_result.value.summary
                if summary_result and summary_result.success
                else "Summary generation failed for this reference. Manual review required."
            )
            reference_results_by_candidate[c_idx].append(ReferenceResult(
                reference_name=ref.reference_name,
                relationship=ref.relationship,
                extracted_facts=extracted_by_ref[key],
                discrepancies=discrepancies_by_ref[key],
                sentiment=sentiment_by_ref[key],
                red_flags=red_flags_by_ref[key],
                confidence_score=confidence_by_ref[key],
                needs_human_review=needs_review_by_ref[key] or (summary_result is None or not summary_result.success),
                reference_summary=summary_text,
            ))

    # -----------------------------------------------------------------
    # Phase 7: cross_check_references + score_overall + routing, per
    # candidate. Pure Python, reused from CandidateNodes.
    # -----------------------------------------------------------------
    cross_flags_by_candidate: dict[int, list[CrossReferenceFlag]] = {}
    overall_confidence_by_candidate: dict[int, float] = {}
    overall_needs_review_by_candidate: dict[int, bool] = {}
    overall_route_by_candidate: dict[int, str] = {}

    for c_idx in range(n_candidates):
        cand_state = {"reference_results": reference_results_by_candidate[c_idx]}
        cross_result = _candidate_nodes.cross_check_references(cand_state)
        cross_flags_by_candidate[c_idx] = cross_result["cross_reference_flags"]

        score_state = {**cand_state, "cross_reference_flags": cross_result["cross_reference_flags"]}
        overall_score_result = _candidate_nodes.score_overall(score_state)
        overall_confidence_by_candidate[c_idx] = overall_score_result["overall_confidence"]
        overall_needs_review_by_candidate[c_idx] = overall_score_result["overall_needs_review"]
        overall_route_by_candidate[c_idx] = _candidate_nodes.route_overall_review(overall_score_result)

    # -----------------------------------------------------------------
    # Phase 8: overall_flag_for_review OR overall_clear, per candidate.
    # -----------------------------------------------------------------
    phase8_items = []
    for c_idx, candidate in enumerate(candidates):
        if overall_route_by_candidate[c_idx] == "overall_flag_for_review":
            system, user_message = rb.overall_flag_for_review_request(
                candidate.candidate_name, candidate.role_applied_for,
                overall_confidence_by_candidate[c_idx],
                reference_results_by_candidate[c_idx], cross_flags_by_candidate[c_idx],
            )
        else:
            system, user_message = rb.overall_clear_request(
                candidate.candidate_name, candidate.role_applied_for,
                overall_confidence_by_candidate[c_idx], reference_results_by_candidate[c_idx],
            )
        phase8_items.append(BatchItem(
            custom_id=f"c{c_idx}:overall",
            system=system, user_message=user_message,
            output_model=OverallSummary, model=model_reasoning,
        ))

    phase8_results = backend.run_batch_sync(phase8_items) if phase8_items else {}
    logger.info(f"phase 8 (overall summaries) done: {len(phase8_items)} requests")

    # -----------------------------------------------------------------
    # Final assembly.
    # -----------------------------------------------------------------
    output = []
    for c_idx, candidate in enumerate(candidates):
        overall_result = phase8_results.get(f"c{c_idx}:overall")
        overall_summary_text = (
            overall_result.value.summary
            if overall_result and overall_result.success
            else "Overall summary generation failed. Manual review required."
        )
        output.append({
            "candidate_name": candidate.candidate_name,
            "role_applied_for": candidate.role_applied_for,
            "claimed_details": candidate.claimed_details,
            "reference_results": reference_results_by_candidate[c_idx],
            "cross_reference_flags": cross_flags_by_candidate[c_idx],
            "overall_confidence": overall_confidence_by_candidate[c_idx],
            "overall_needs_review": overall_needs_review_by_candidate[c_idx],
            "overall_summary": overall_summary_text,
        })

    logger.info(f"batch pipeline done: {len(output)} candidates processed")
    return output
