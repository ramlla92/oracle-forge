# kb/evaluation/ — KB v3 (Evaluation): DAB Scoring Method

Documentation of how DataAgentBench scores agent outputs. Used by `eval/score.py` and the evaluation harness to ensure correct pass@1 computation.

## Documents

| File | Contents | Injection Test |
|------|----------|---------------|
| `dab_read.md` | DAB paper key findings: 54 queries, 12 datasets, 4 DB types, current SOTA 54.3% | ✓ verified |
| `ddb_read.md` | DuckDB-specific evaluation notes: table scope, type system quirks, strptime pitfalls | ✓ verified |
| `scoring_method.md` | pass@1 definition, how ground truth matching works (numeric tolerance, name fuzzy match) | ✓ verified |
| `injection_tests.md` | Verified test query + expected answer for each document above | — |
| `CHANGELOG.md` | Version history for this KB layer | — |

## Scoring Rules

From `scoring_method.md`:
- **Numeric answers**: correct if agent output contains a number within ±5% of ground truth
- **Name answers**: correct if ground truth name appears in agent output (case-insensitive, fuzzy match within 3 characters)
- **List answers**: correct if all required items appear in agent output (order-insensitive)
- **pass@1**: fraction of queries where `any_pass = True` across all trials

These rules are implemented in `eval/run_benchmark.py` and `eval/score.py`.
