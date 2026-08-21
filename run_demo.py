"""
Runs the Reference Check Analyzer (REF1 / open-text flow) against all
sample cases and prints a readable before/after summary for each.

Usage:
    export ANTHROPIC_API_KEY=sk-...   # or set LLM_PROVIDER + that
                                       # provider's credentials
    python run_demo.py            # runs all sample cases
    python run_demo.py clean      # runs just one case
"""

import sys

from refcheck.graphs.reference_graph import build_reference_graphs
from refcheck.llm.providers import get_provider
from refcheck.data.sample_data import ALL_CASES


def print_result(case_name: str, result: dict):
    print("=" * 70)
    print(f"CASE: {case_name}")
    print("=" * 70)
    print(f"Candidate: {result['candidate_name']}")
    print(f"Confidence score: {result['confidence_score']}/100")
    print(f"Needs human review: {result['needs_human_review']}")
    print(f"Sentiment: {result.get('sentiment')}")

    if result.get("discrepancies"):
        print("\nDiscrepancies:")
        for d in result["discrepancies"]:
            print(f"  - [{d.severity}] {d.field}: claimed={d.claimed_value!r} "
                  f"vs stated={d.stated_value!r}")
            if d.note:
                print(f"      note: {d.note}")
    else:
        print("\nDiscrepancies: none")

    if result.get("red_flags"):
        print("\nRed flags:")
        for rf in result["red_flags"]:
            print(f"  - {rf}")

    print(f"\nFinal summary:\n{result.get('final_summary')}\n")


def main():
    # sample_data.py's cases are all REF1 (open text); the REF2 flow is
    # exercised via run_demo_multi.py instead, since it only really
    # makes sense in a multi-reference candidate context.
    open_ended_graph, _yes_no_graph = build_reference_graphs(get_provider())
    cases = sys.argv[1:] or list(ALL_CASES.keys())

    for case_name in cases:
        if case_name not in ALL_CASES:
            print(f"Unknown case: {case_name}. Options: {list(ALL_CASES.keys())}")
            continue
        result = open_ended_graph.invoke(ALL_CASES[case_name])
        print_result(case_name, result)


if __name__ == "__main__":
    main()
