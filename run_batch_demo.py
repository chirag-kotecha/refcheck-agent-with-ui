"""
Runs the batch pipeline (refcheck.pipelines.batch_runner) against sample
candidates via a real Batch API call.

This will actually submit batch job(s) and poll until they complete --
expect this to take noticeably longer than run_demo_multi.py. Don't run
this expecting an instant result; it's meant to run unattended.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python run_batch_demo.py                          # all cases, Anthropic batch
    python run_batch_demo.py cross_reference_conflict  # one case
    python run_batch_demo.py --provider bedrock        # use Bedrock batch instead
                                                        # (requires S3/IAM config,
                                                        # see .env.example)
"""

import argparse

from refcheck.pipelines.batch_runner import CandidateBatchInput, run_batch_pipeline
from refcheck.data.sample_data_multi import ALL_MULTI_CASES


def to_batch_input(case: dict) -> CandidateBatchInput:
    return CandidateBatchInput(
        candidate_name=case["candidate_name"],
        role_applied_for=case["role_applied_for"],
        claimed_details=case["claimed_details"],
        references=case["references"],
    )


def print_result(result: dict):
    print("=" * 70)
    print(f"CANDIDATE: {result['candidate_name']}")
    print("=" * 70)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", nargs="*", help="sample case names (default: all)")
    parser.add_argument(
        "--provider", default="anthropic", choices=["anthropic", "bedrock"],
        help="which batch backend to use (default: anthropic)",
    )
    args = parser.parse_args()

    case_names = args.cases or list(ALL_MULTI_CASES.keys())
    unknown = [c for c in case_names if c not in ALL_MULTI_CASES]
    if unknown:
        print(f"Unknown case(s): {unknown}. Options: {list(ALL_MULTI_CASES.keys())}")
        return

    batch_inputs = [to_batch_input(ALL_MULTI_CASES[c]) for c in case_names]
    print(f"Submitting batch (provider={args.provider}) for {len(batch_inputs)} candidate(s): {case_names}")
    print("(this polls until the batch finishes -- may take a while, see module docstrings)\n")

    results = run_batch_pipeline(batch_inputs, batch_provider=args.provider)
    for result in results:
        print_result(result)


if __name__ == "__main__":
    main()
