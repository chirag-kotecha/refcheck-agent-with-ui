"""
Candidate-level node methods. CandidateNodes owns the two compiled
single-reference subgraphs (built once, in __init__, from one shared
ReferenceCheckNodes instance) and dispatches each reference to the
correct one based on its `type` field -- REF_TYPE_OPEN_TEXT ("REF1") or
REF_TYPE_YES_NO ("REF2").
"""

from typing import Optional

from refcheck import config
from refcheck import request_builders as rb
from refcheck.graphs.reference_graph import build_reference_graphs
from refcheck.llm.base import BaseLLMProvider, StructuredCallError
from refcheck.logging_config import get_logger
from refcheck.validation import validate_raw_input
from refcheck.schemas import (
    CandidateState,
    CrossReferenceFlag,
    ExtractedFacts,
    OverallSummary,
    REF_TYPE_OPEN_TEXT,
    REF_TYPE_YES_NO,
    ReferenceResult,
)


class CandidateNodes:
    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        """`llm_provider` may be None for callers that only need the
        pure-Python methods (cross_check_references, score_overall,
        route_overall_review) -- e.g. the batch pipeline. run_reference
        and the two overall-summary methods require a provider."""
        self.llm = llm_provider
        self.logger = get_logger(self.__class__.__name__)
        if llm_provider is not None:
            self._open_ended_graph, self._yes_no_graph = build_reference_graphs(llm_provider)
        else:
            self._open_ended_graph = self._yes_no_graph = None

    def run_reference(self, payload: dict) -> dict:
        """
        Invoked once per reference (via Send). `payload` is built in
        graphs/candidate_graph.py's fan_out_references -- candidate
        context + one ReferenceInput's fields flattened into whichever
        single-reference subgraph input that reference's `type` needs.
        """
        reference_name = payload.pop("reference_name")
        relationship = payload.pop("relationship")
        reference_type = payload.pop("type")
        candidate = payload.get("candidate_name", "unknown")

        self.logger.info(
            f"run_reference start candidate={candidate} reference={reference_name} "
            f"type={reference_type}"
        )

        try:
            if reference_type == REF_TYPE_OPEN_TEXT:
                validate_raw_input(payload["raw_input"], context=f"{candidate}/{reference_name}")
                result_state = self._open_ended_graph.invoke(payload)
            elif reference_type == REF_TYPE_YES_NO:
                result_state = self._yes_no_graph.invoke(payload)
            else:
                raise ValueError(f"unknown reference type: {reference_type!r}")
        except Exception as e:
            self.logger.error(
                f"run_reference failed candidate={candidate} reference={reference_name} error={e!r}"
            )
            result = ReferenceResult(
                reference_name=reference_name,
                relationship=relationship,
                extracted_facts=ExtractedFacts(),
                discrepancies=[],
                sentiment="unclear",
                red_flags=[f"Automated processing failed for this reference: {e}"],
                confidence_score=0.0,
                needs_human_review=True,
                reference_summary=(
                    f"This reference could not be processed automatically due to an "
                    f"error ({e.__class__.__name__}). Manual review required."
                ),
            )
            return {"reference_results": [result]}

        result = ReferenceResult(
            reference_name=reference_name,
            relationship=relationship,
            extracted_facts=result_state.get("extracted_facts") or ExtractedFacts(),
            discrepancies=result_state.get("discrepancies", []),
            sentiment=result_state.get("sentiment", "neutral"),
            red_flags=result_state.get("red_flags", []),
            confidence_score=result_state["confidence_score"],
            needs_human_review=result_state["needs_human_review"],
            reference_summary=result_state.get("final_summary", ""),
        )
        self.logger.info(f"run_reference done candidate={candidate} reference={reference_name}")
        return {"reference_results": [result]}

    def cross_check_references(self, state: CandidateState) -> dict:
        """Pure Python. Flags fields where references disagree with
        EACH OTHER (distinct from per-reference discrepancies vs. claims)."""
        results = state["reference_results"]
        flags = []

        fields_to_check = ["job_title", "company"]
        for field in fields_to_check:
            stated_values = {}
            for r in results:
                val = getattr(r.extracted_facts, field)
                if val:
                    stated_values.setdefault(val.strip().lower(), []).append(r.reference_name)
            if len(stated_values) > 1:
                involved = [name for names in stated_values.values() for name in names]
                flags.append(CrossReferenceFlag(
                    field=field,
                    description=(
                        f"References disagree on {field}: "
                        + "; ".join(f"{names} said {val!r}" for val, names in stated_values.items())
                    ),
                    severity="major" if field == "company" else "moderate",
                    involved_references=involved,
                ))

        performance_by_ref = {
            r.reference_name: r.extracted_facts.performance_rating
            for r in results if r.extracted_facts.performance_rating
        }
        ratings = set(performance_by_ref.values())
        if "strong" in ratings and "weak" in ratings:
            flags.append(CrossReferenceFlag(
                field="performance_rating",
                description=(
                    "References give conflicting performance assessments: "
                    + ", ".join(f"{name}={rating}" for name, rating in performance_by_ref.items())
                ),
                severity="major",
                involved_references=list(performance_by_ref.keys()),
            ))

        self.logger.info(f"cross_check_references found {len(flags)} flags")
        return {"cross_reference_flags": flags}

    def score_overall(self, state: CandidateState) -> dict:
        """Pure Python."""
        results = state["reference_results"]
        avg_score = sum(r.confidence_score for r in results) / len(results)

        for flag in state.get("cross_reference_flags", []):
            avg_score -= config.SEVERITY_PENALTY[flag.severity]
        avg_score = max(0.0, min(100.0, avg_score))

        any_ref_needs_review = any(r.needs_human_review for r in results)
        has_cross_flags = bool(state.get("cross_reference_flags"))
        needs_review = (
            avg_score < config.OVERALL_REVIEW_THRESHOLD or any_ref_needs_review or has_cross_flags
        )

        self.logger.info(f"score_overall avg_score={avg_score} needs_review={needs_review}")
        return {"overall_confidence": avg_score, "overall_needs_review": needs_review}

    def route_overall_review(self, state: CandidateState) -> str:
        return "overall_flag_for_review" if state["overall_needs_review"] else "overall_clear"

    def overall_flag_for_review(self, state: CandidateState) -> dict:
        system, user_message = rb.overall_flag_for_review_request(
            state["candidate_name"], state["role_applied_for"], state["overall_confidence"],
            state["reference_results"], state.get("cross_reference_flags", []),
        )
        result = self.llm.structured_call(
            system, user_message, OverallSummary, model=self.llm.get_model("reasoning")
        )
        return {"overall_summary": result.summary}

    def overall_clear(self, state: CandidateState) -> dict:
        system, user_message = rb.overall_clear_request(
            state["candidate_name"], state["role_applied_for"], state["overall_confidence"],
            state["reference_results"],
        )
        result = self.llm.structured_call(
            system, user_message, OverallSummary, model=self.llm.get_model("reasoning")
        )
        return {"overall_summary": result.summary}
