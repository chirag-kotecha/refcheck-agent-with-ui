"""
Node methods for the single-reference flows, grouped into a class so
they can be constructed with a specific LLM provider injected.

ReferenceCheckNodes holds methods for BOTH reference input types:
  - REF1 (open text): extract_facts / sentiment_and_redflags /
    diff_facts / explain_discrepancies / flag_for_human_review / auto_summarize
  - REF2 (yes/no form): evaluate_yes_no_form / has_comments /
    sentiment_from_comments
Both converge on the same score_confidence / route_review /
flag_for_human_review / auto_summarize methods -- see
refcheck/graphs/reference_graph.py for how each input type is wired
into its own compiled graph sharing one instance of this class.
"""

from datetime import datetime
from typing import Optional

from refcheck import config
from refcheck import request_builders as rb
from refcheck.llm.base import BaseLLMProvider
from refcheck.logging_config import get_logger
from refcheck.validation import validate_raw_input
from refcheck.schemas import (
    ClaimedDetails,
    Discrepancy,
    DiscrepancyNotes,
    ExtractedFacts,
    FinalSummary,
    ReferenceCheckState,
    SentimentAndRedFlags,
    YesNoReferenceForm,
)


class ReferenceCheckNodes:
    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        """`llm_provider` may be None for callers that only need the
        pure-Python methods (diff_facts, score_confidence, route_review,
        evaluate_yes_no_form, has_discrepancies, has_comments) -- e.g.
        the batch pipeline reuses those without an LLM provider."""
        self.llm = llm_provider
        self.logger = get_logger(self.__class__.__name__)

    @staticmethod
    def _month_diff(a: str, b: str) -> Optional[int]:
        try:
            da = datetime.strptime(a, "%Y-%m")
            db = datetime.strptime(b, "%Y-%m")
        except (ValueError, TypeError):
            return None
        return abs((da.year - db.year) * 12 + (da.month - db.month))

    # =======================================================================
    # REF1 flow (open-text transcript/email)
    # =======================================================================

    def extract_facts(self, state: ReferenceCheckState) -> dict:
        claimed: ClaimedDetails = state["claimed_details"]
        candidate = state["candidate_name"]
        validate_raw_input(state["raw_input"], context=f"extract_facts/{candidate}")

        system, user_message = rb.extract_facts_request(
            candidate, state["role_applied_for"], claimed, state["raw_input"]
        )
        self.logger.info(f"extract_facts start candidate={candidate}")
        facts = self.llm.structured_call(
            system, user_message, ExtractedFacts, model=self.llm.get_model("extraction")
        )
        self.logger.info(f"extract_facts done candidate={candidate}")
        return {"extracted_facts": facts}

    def sentiment_and_redflags(self, state: ReferenceCheckState) -> dict:
        candidate = state["candidate_name"]
        validate_raw_input(state["raw_input"], context=f"sentiment_and_redflags/{candidate}")

        system, user_message = rb.sentiment_and_redflags_request(state["raw_input"])
        self.logger.info(f"sentiment_and_redflags start candidate={candidate}")
        result = self.llm.structured_call(
            system, user_message, SentimentAndRedFlags, model=self.llm.get_model("extraction")
        )
        self.logger.info(f"sentiment_and_redflags done candidate={candidate} sentiment={result.sentiment}")
        return {"sentiment": result.sentiment, "red_flags": result.red_flags}

    def diff_facts(self, state: ReferenceCheckState) -> dict:
        """Pure Python, no LLM call."""
        claimed: ClaimedDetails = state["claimed_details"]
        facts: ExtractedFacts = state["extracted_facts"]
        discrepancies: list[Discrepancy] = []

        if facts.company and facts.company.strip().lower() != claimed.company.strip().lower():
            discrepancies.append(Discrepancy(
                field="company", claimed_value=claimed.company,
                stated_value=facts.company, severity="major",
            ))

        if facts.job_title and facts.job_title.strip().lower() != claimed.job_title.strip().lower():
            seniority_words = ["senior", "lead", "principal", "manager", "director", "head"]
            claimed_senior = any(w in claimed.job_title.lower() for w in seniority_words)
            stated_senior = any(w in facts.job_title.lower() for w in seniority_words)
            severity = "major" if (claimed_senior and not stated_senior) else "moderate"
            discrepancies.append(Discrepancy(
                field="job_title", claimed_value=claimed.job_title,
                stated_value=facts.job_title, severity=severity,
            ))

        if facts.start_date:
            diff = self._month_diff(claimed.start_date, facts.start_date)
            if diff is not None and diff > config.MINOR_MONTH_TOLERANCE:
                severity = "moderate" if diff <= config.MODERATE_MONTH_TOLERANCE else "major"
                discrepancies.append(Discrepancy(
                    field="start_date", claimed_value=claimed.start_date,
                    stated_value=facts.start_date, severity=severity,
                ))
            elif diff is None:
                self.logger.warning(
                    f"start_date could not be parsed for diffing: "
                    f"claimed={claimed.start_date!r} stated={facts.start_date!r}"
                )

        if facts.end_date and claimed.end_date:
            diff = self._month_diff(claimed.end_date, facts.end_date)
            if diff is not None and diff > config.MINOR_MONTH_TOLERANCE:
                severity = "moderate" if diff <= config.MODERATE_MONTH_TOLERANCE else "major"
                discrepancies.append(Discrepancy(
                    field="end_date", claimed_value=claimed.end_date,
                    stated_value=facts.end_date, severity=severity,
                ))
            elif diff is None:
                self.logger.warning(
                    f"end_date could not be parsed for diffing: "
                    f"claimed={claimed.end_date!r} stated={facts.end_date!r}"
                )
        elif facts.end_date and not claimed.end_date:
            discrepancies.append(Discrepancy(
                field="end_date", claimed_value="still employed",
                stated_value=facts.end_date, severity="major",
            ))

        self.logger.info(f"diff_facts found {len(discrepancies)} discrepancies")
        return {"discrepancies": discrepancies}

    def has_discrepancies(self, state: ReferenceCheckState) -> str:
        return "explain_discrepancies" if state["discrepancies"] else "score_confidence"

    def explain_discrepancies(self, state: ReferenceCheckState) -> dict:
        discrepancies = state["discrepancies"]
        system, user_message = rb.explain_discrepancies_request(discrepancies)
        result = self.llm.structured_call(
            system, user_message, DiscrepancyNotes, model=self.llm.get_model("reasoning")
        )
        notes_by_field = {n.field: n.note for n in result.notes}
        updated = [
            d.model_copy(update={"note": notes_by_field.get(d.field, d.note)})
            for d in discrepancies
        ]
        return {"discrepancies": updated}

    # =======================================================================
    # REF2 flow (yes/no form)
    # =======================================================================

    def evaluate_yes_no_form(self, state: ReferenceCheckState) -> dict:
        """Pure Python, no LLM call -- the form's answers ARE the facts."""
        claimed: ClaimedDetails = state["claimed_details"]
        form: YesNoReferenceForm = state["yes_no_form"]
        discrepancies: list[Discrepancy] = []
        red_flags: list[str] = []

        field_map = [
            ("confirmed_title", "job_title", claimed.job_title),
            ("confirmed_dates", "employment_dates", f"{claimed.start_date} - {claimed.end_date or 'present'}"),
            ("confirmed_company", "company", claimed.company),
        ]
        for form_field, discrepancy_field, claimed_value in field_map:
            answer = getattr(form, form_field)
            if answer == "no":
                discrepancies.append(Discrepancy(
                    field=discrepancy_field, claimed_value=claimed_value,
                    stated_value="reference did not confirm", severity="major",
                ))
            elif answer == "unsure":
                discrepancies.append(Discrepancy(
                    field=discrepancy_field, claimed_value=claimed_value,
                    stated_value="reference was unsure", severity="minor",
                ))

        if form.performance_concerns == "yes":
            red_flags.append("Reference indicated performance concerns")
        elif form.performance_concerns == "unsure":
            red_flags.append("Reference was unsure about performance concerns")

        if form.would_rehire == "no":
            red_flags.append("Reference would not rehire this candidate")
        elif form.would_rehire == "unsure":
            red_flags.append("Reference was unsure about rehiring this candidate")

        self.logger.info(
            f"evaluate_yes_no_form found {len(discrepancies)} discrepancies, "
            f"{len(red_flags)} red flags"
        )
        return {"discrepancies": discrepancies, "red_flags": red_flags, "sentiment": "neutral"}

    def has_comments(self, state: ReferenceCheckState) -> str:
        form: YesNoReferenceForm = state["yes_no_form"]
        return "sentiment_from_comments" if (form.additional_comments or "").strip() else "score_confidence"

    def sentiment_from_comments(self, state: ReferenceCheckState) -> dict:
        """Reuses the exact same prompt/schema as the REF1 flow's
        sentiment_and_redflags."""
        form: YesNoReferenceForm = state["yes_no_form"]
        system, user_message = rb.sentiment_and_redflags_request(form.additional_comments)
        result = self.llm.structured_call(
            system, user_message, SentimentAndRedFlags, model=self.llm.get_model("extraction")
        )
        merged_red_flags = state.get("red_flags", []) + result.red_flags
        return {"sentiment": result.sentiment, "red_flags": merged_red_flags}

    # =======================================================================
    # Shared by both flows
    # =======================================================================

    def score_confidence(self, state: ReferenceCheckState) -> dict:
        score = 100.0
        for d in state.get("discrepancies", []):
            score -= config.SEVERITY_PENALTY[d.severity]
        score -= config.RED_FLAG_PENALTY * len(state.get("red_flags", []))
        score -= config.SENTIMENT_PENALTY.get(state.get("sentiment", "neutral"), 0)
        score = max(0.0, min(100.0, score))

        has_major = any(d.severity == "major" for d in state.get("discrepancies", []))
        needs_review = score < config.REVIEW_THRESHOLD or has_major or bool(state.get("red_flags"))

        self.logger.info(f"score_confidence score={score} needs_review={needs_review}")
        return {"confidence_score": score, "needs_human_review": needs_review}

    def route_review(self, state: ReferenceCheckState) -> str:
        return "flag_for_human_review" if state["needs_human_review"] else "auto_summarize"

    def flag_for_human_review(self, state: ReferenceCheckState) -> dict:
        system, user_message = rb.flag_for_human_review_request(
            state["candidate_name"], state["role_applied_for"], state["confidence_score"],
            state.get("sentiment"), state.get("discrepancies", []), state.get("red_flags", []),
        )
        result = self.llm.structured_call(
            system, user_message, FinalSummary, model=self.llm.get_model("reasoning")
        )
        return {"final_summary": result.summary}

    def auto_summarize(self, state: ReferenceCheckState) -> dict:
        system, user_message = rb.auto_summarize_request(
            state["candidate_name"], state["role_applied_for"], state["confidence_score"],
            state.get("sentiment"), state["claimed_details"],
        )
        result = self.llm.structured_call(
            system, user_message, FinalSummary, model=self.llm.get_model("reasoning")
        )
        return {"final_summary": result.summary}
