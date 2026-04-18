# eval/ — Evaluation Harness

Benchmark runner, scoring, and score progression log for Oracle Forge against the [UC Berkeley DataAgentBench](https://github.com/ucbepic/DataAgentBench).

## Files

| File | Purpose |
|------|---------|
| `run_benchmark.py` | Full DAB benchmark runner — executes N trials per query, writes timestamped JSON to `run_logs/` |
| `run_query.py` | Single-query test runner — for interactive debugging |
| `score.py` | Computes pass@1 from a `run_logs/benchmark_*.json` results file |
| `score_log.md` | Score progression table — every dated run with methodology notes |
| `score_log.json` | Machine-readable version of the score log |
| `run_logs/` | Per-run timestamped JSON logs (200+ files, Apr 11–18 2026) |

## Quick Start

```bash
# Run full yelp benchmark, 5 trials per query
python eval/run_benchmark.py --dataset yelp --trials 5

# Run a single test question
python eval/run_query.py --question "What is the average rating of businesses in Las Vegas?"

# Score an existing results file
python eval/score.py --results eval/run_logs/benchmark_yelp_20260415_183320.json --verbose
```

## Score Progression (Yelp dataset, 7 queries)

| Date | pass@1 | Notes |
|------|--------|-------|
| 2026-04-11 | 0% | Baseline |
| 2026-04-11 | 14% | Pattern A fix (no code fences) |
| 2026-04-14 | 57% | Pattern B fix (MongoDB pipeline format) |
| 2026-04-14 | 86% | Patterns C+D fix (DuckDB table scope, date format) |
| 2026-04-14 | 100% | Python post-processing for text extraction |

Full run history (66 entries across 8 datasets) in `score_log.md`.

## Results Format

Each `run_logs/benchmark_<dataset>_<timestamp>.json` contains:

```json
{
  "dataset": "yelp",
  "timestamp": "20260415_183320",
  "trials": 5,
  "pass_count": 7,
  "total_queries": 7,
  "pass_at_k": 0.885,
  "results": [
    {
      "query_id": "query1",
      "question": "...",
      "ground_truth": "...",
      "trials": [
        {"trial": 1, "answer": "...", "passed": true, "reason": "..."}
      ],
      "any_pass": true
    }
  ]
}
```

DAB-formatted submission JSON (dataset, query_id, run, answer) is in `../results/dab_submission.json`.
