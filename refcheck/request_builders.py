"""
Pure functions that build (system_prompt, user_message) pairs for every
LLM call in this project. Used by BOTH the real-time graphs
(refcheck/nodes/*.py) and the batch pipeline
(refcheck/pipelines/batch_runner.py) so the two execution paths can
never drift apart in wording. Nothing here makes an API call.
"""

from refcheck import prompts
from refcheck.schemas import ClaimedDetails, Discrepancy, ReferenceResult


def extract_facts_request(candidate_name: str, role_applied_for: str,
                           claimed_details: ClaimedDetails, raw_input: str) -> tuple[str, str]:
    user_message = (
        f"Candidate: {candidate_name}\n"
        f"Role applied for: {role_applied_for}\n"
        f"Candidate's claimed details (context only, do NOT just copy these "
        f"back -- extract only what the reference actually says):\n"
        f"{claimed_details.model_dump_json(indent=2)}\n\n"
        f"Reference transcript/email:\n---\n{raw_input}\n---"
    )
    return prompts.EXTRACT_FACTS_SYSTEM, user_message


def sentiment_and_redflags_request(raw_input: str) -> tuple[str, str]:
    user_message = f"Reference transcript/email:\n---\n{raw_input}\n---"
    return prompts.SENTIMENT_AND_REDFLAGS_SYSTEM, user_message


def explain_discrepancies_request(discrepancies: list[Discrepancy]) -> tuple[str, str]:
    items = "\n".join(
        f"- field={d.field}, claimed={d.claimed_value!r}, stated={d.stated_value!r}, "
        f"severity={d.severity}"
        for d in discrepancies
    )
    user_message = f"Discrepancies:\n{items}"
    return prompts.EXPLAIN_DISCREPANCIES_SYSTEM, user_message


def flag_for_human_review_request(candidate_name: str, role_applied_for: str,
                                   confidence_score: float, sentiment: str,
                                   discrepancies: list[Discrepancy],
                                   red_flags: list[str]) -> tuple[str, str]:
    discrepancy_text = "\n".join(
        f"- {d.field}: claimed {d.claimed_value!r}, reference said {d.stated_value!r} "
        f"({d.severity}). {d.note or ''}"
        for d in discrepancies
    ) or "None"
    red_flag_text = "\n".join(f"- {rf}" for rf in red_flags) or "None"

    user_message = (
        f"Candidate: {candidate_name}\n"
        f"Role: {role_applied_for}\n"
        f"Confidence score: {confidence_score}/100\n"
        f"Sentiment: {sentiment}\n\n"
        f"Discrepancies:\n{discrepancy_text}\n\n"
        f"Red flags:\n{red_flag_text}"
    )
    return prompts.FLAG_FOR_HUMAN_REVIEW_SYSTEM, user_message


def auto_summarize_request(candidate_name: str, role_applied_for: str,
                            confidence_score: float, sentiment: str,
                            claimed_details: ClaimedDetails) -> tuple[str, str]:
    user_message = (
        f"Candidate: {candidate_name}\n"
        f"Role: {role_applied_for}\n"
        f"Confidence score: {confidence_score}/100\n"
        f"Sentiment: {sentiment}\n"
        f"Claimed details confirmed: {claimed_details.model_dump_json()}"
    )
    return prompts.AUTO_SUMMARIZE_SYSTEM, user_message


def _reference_context_lines(reference_results: list[ReferenceResult],
                              cross_reference_flags: list) -> str:
    lines = []
    for r in reference_results:
        lines.append(
            f"- {r.reference_name} ({r.relationship}): confidence={r.confidence_score}, "
            f"sentiment={r.sentiment}, needs_review={r.needs_human_review}\n"
            f"  summary: {r.reference_summary}"
        )
    for f in cross_reference_flags:
        lines.append(f"- CROSS-REFERENCE FLAG [{f.severity}] {f.field}: {f.description}")
    return "\n".join(lines)


def overall_flag_for_review_request(candidate_name: str, role_applied_for: str,
                                     overall_confidence: float,
                                     reference_results: list[ReferenceResult],
                                     cross_reference_flags: list) -> tuple[str, str]:
    user_message = (
        f"Candidate: {candidate_name}\n"
        f"Role: {role_applied_for}\n"
        f"Overall confidence: {overall_confidence}/100\n\n"
        f"Per-reference results and cross-reference flags:\n"
        f"{_reference_context_lines(reference_results, cross_reference_flags)}"
    )
    return prompts.OVERALL_FLAG_FOR_REVIEW_SYSTEM, user_message


def overall_clear_request(candidate_name: str, role_applied_for: str,
                           overall_confidence: float,
                           reference_results: list[ReferenceResult]) -> tuple[str, str]:
    user_message = (
        f"Candidate: {candidate_name}\n"
        f"Role: {role_applied_for}\n"
        f"Overall confidence: {overall_confidence}/100\n\n"
        f"Per-reference results:\n{_reference_context_lines(reference_results, [])}"
    )
    return prompts.OVERALL_CLEAR_SYSTEM, user_message
