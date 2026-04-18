"""
Compute pass@1 from a benchmark results JSON file.

Usage:
    python eval/score.py --results eval/run_logs/benchmark_yelp_<timestamp>.json
    python eval/score.py --results eval/run_logs/benchmark_yelp_<timestamp>.json --verbose
"""

import argparse
import json
import sys
from pathlib import Path


def compute_pass_at_1(results_path: str, verbose: bool = False) -> dict:
    """
    Compute pass@1 from a benchmark results JSON file.

    pass@1 = fraction of queries where at least one trial passed.

    Args:
        results_path: Path to the benchmark results JSON file.
        verbose: Print per-query details.

    Returns:
        dict with keys: dataset, total_queries, passed_queries, pass_at_1, per_query
    """
    path = Path(results_path)
    if not path.exists():
        raise FileNotFoundError(f"Results file not found: {results_path}")

    with open(path) as f:
        data = json.load(f)

    dataset = data.get("dataset", "unknown")
    results = data.get("results", [])
    total = len(results)
    passed = sum(1 for r in results if r.get("any_pass", False))
    pass_at_1 = passed / total if total > 0 else 0.0

    per_query = []
    for r in results:
        any_pass = r.get("any_pass", False)
        trials = r.get("trials", [])
        trial_passes = sum(1 for t in trials if t.get("passed", False))
        per_query.append({
            "query_id": r["query_id"],
            "any_pass": any_pass,
            "trials_passed": trial_passes,
            "total_trials": len(trials),
        })

    if verbose:
        print(f"\n=== {dataset} — {path.name} ===")
        for q in per_query:
            status = "PASS" if q["any_pass"] else "FAIL"
            print(f"  [{status}] {q['query_id']} — {q['trials_passed']}/{q['total_trials']} trials passed")
        print(f"\nResult: {passed}/{total} queries passed — pass@1 = {pass_at_1:.1%}\n")

    return {
        "dataset": dataset,
        "total_queries": total,
        "passed_queries": passed,
        "pass_at_1": pass_at_1,
        "per_query": per_query,
    }


def main():
    parser = argparse.ArgumentParser(description="Compute pass@1 from benchmark results JSON.")
    parser.add_argument("--results", required=True, help="Path to benchmark results JSON file")
    parser.add_argument("--verbose", action="store_true", help="Print per-query breakdown")
    args = parser.parse_args()

    try:
        score = compute_pass_at_1(args.results, verbose=args.verbose)
        if not args.verbose:
            print(f"{score['dataset']}: {score['passed_queries']}/{score['total_queries']} — pass@1 = {score['pass_at_1']:.1%}")
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
