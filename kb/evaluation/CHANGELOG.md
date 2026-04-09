# CHANGELOG — kb/evaluation/

All changes to evaluation knowledge base documents are recorded here.
Format: `[DATE] | [DOCUMENT] | [CHANGE TYPE] | [WHAT CHANGED] | [REASON]`
Change types: ADDED | UPDATED | REMOVED | INJECTION-TEST-RESULT

Maintained by: Intelligence Officers
Reviewed at: every mob session

---

## 2026-04-08

| Date | Document | Change Type | What Changed | Reason |
|------|----------|-------------|--------------|--------|
| 2026-04-08 | `dab_read.md` | ADDED | Initial document created. Covers 54-query set, pass@1 definition, 5-trial minimum, run_benchmark.py interface, GitHub PR submission format, internal harness requirement. | Required KB v1 deliverable. Must exist before any evaluation run. |
| 2026-04-08 | `ddb_read.md` | ADDED | Initial document created. Covers DuckDB-specific evaluation notes: routing plan requirement, query trace format, pre-aggregated table pitfall, ±0.01 float tolerance, result ordering requirement. | DuckDB is one of four DAB database types. Evaluation behaviour differs from PostgreSQL. |
| 2026-04-08 | `scoring_method.md` | ADDED | Initial document created. Maps all four DAB failure categories to probe design rules, query trace signals that confirm failure, and fix directions. | Required KB v1 deliverable. Needed before adversarial probe library is run against the agent. |

---

## Instructions for Future Entries

- After every evaluation harness run, add a row here if the run revealed that any document in this directory was incomplete or incorrect.
- If the DAB repository updates its scoring method or submission format, update the relevant document and log here immediately — stale evaluation docs cause submission errors.
- If an injection test on any document in this directory fails, add an INJECTION-TEST-RESULT row and revise the document before the next mob session.
- After benchmark submission, add a row recording the final pass@1 score and the PR link for traceability.