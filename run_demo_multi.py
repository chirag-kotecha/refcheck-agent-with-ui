"""
Runs the candidate-level (multi-reference) graph against sample cases.
Sample cases include REF1 (open text), REF2 (yes/no), and mixed.

Usage:
    export ANTHROPIC_API_KEY=sk-...   # or set LLM_PROVIDER + credentials
    python run_demo_multi.py                          # all cases
    python run_demo_multi.py cross_reference_conflict  # one case
"""

import sys

from refcheck import config
from refcheck.graphs.candidate_graph import build_candidate_graph
from refcheck.llm.providers import get_provider
from refcheck.data.sample_data_multi import ALL_MULTI_CASES


def print_result(case_name: str, result: dict):
    print("=" * 70)
    print(f"CASE: {case_name}")
    print("=" * 70)
    print(f"Candidate: {result['candidate_name']}")
    print(f"Overall confidence: {result['overall_confidence']:.1f}/100")
    print(f"Overall needs human review: {result['overall_needs_review']}")

    print(f"\nPer-reference results ({len(result['reference_results'])} references):")
    for r in result["reference_results"]:
        print(f"  - {r.reference_name} ({r.relationship}): "
              f"confidence={r.confidence_score}, sentiment={r.sentiment}, "
              f"needs_review={r.needs_human_review}")
        for d in r.discrepancies:
            print(f"      discrepancy [{d.severity}] {d.field}: "
                  f"{d.claimed_value!r} vs {d.stated_value!r}")
        for rf in r.red_flags:
            print(f"      red flag: {rf}")

    if result.get("cross_reference_flags"):
        print("\nCross-reference flags:")
        for f in result["cross_reference_flags"]:
            print(f"  - [{f.severity}] {f.field}: {f.description}")
    else:
        print("\nCross-reference flags: none")

    print(f"\nOverall summary:\n{result.get('overall_summary')}\n")


def main():
    app = build_candidate_graph(get_provider())
    cases = sys.argv[1:] or list(ALL_MULTI_CASES.keys())

    for case_name in cases:
        if case_name not in ALL_MULTI_CASES:
            print(f"Unknown case: {case_name}. Options: {list(ALL_MULTI_CASES.keys())}")
            continue
        result = app.invoke(
            ALL_MULTI_CASES[case_name],
            config={"max_concurrency": config.MAX_CONCURRENT_REFERENCES},
        )
        print_result(case_name, result)


if __name__ == "__main__":
    main()
