# MEMORY.md — Oracle Forge Knowledge Base Index

This is the master index for the Oracle Forge LLM Knowledge Base.
The agent loads THIS file first at every session start. It then loads
only the specific topic files needed for the current query — not all
documents at once.

Built using the Karpathy KB method: minimum content, maximum precision,
verified by injection test. Every document listed here has passed an
injection test before being committed.

---

## How the Agent Uses This Index

1. **Session start:** Load `MEMORY.md` (this file) into context.
2. **Before answering a query:** Identify which topic files are relevant
   using the index below. Load only those files.
3. **After a failure or correction:** Load `kb/corrections/corrections_log.md`
   and apply the relevant fix before retrying.
4. **After a session:** Run autoDream consolidation — write new correction
   entries and update the relevant topic file via the CHANGELOG.

---

## Architecture Documents
*Load these before writing any agent code or configuring any tool.*

| File | What it answers | Load when |
|------|----------------|-----------|
| `kb/architecture/claude_code_memory.md` | How Claude Code's three-layer memory system works (MEMORY.md → topic files → session transcripts) | Setting up agent memory architecture |
| `kb/architecture/openai_data_agent_context.md` | OpenAI data agent's six context layers; which three are mandatory for Oracle Forge | Designing context injection strategy |
| `kb/architecture/autodream_consolidation.md` | When and how to consolidate session transcripts into KB entries | End of every mob session |
| `kb/architecture/tool_scoping_and_parallelism.md` | Why narrow tool scoping prevents routing failures; minimum tool set for tools.yaml; parallel execution rules | Configuring MCP tools.yaml |
| `kb/architecture/self_correction_loop.md` | Four-step loop: execute → diagnose → recover → log | Agent returns zero rows or an error |
| `kb/architecture/dab_failure_modes.md` | All four DAB failure categories with detection signals and fix directions | Diagnosing any agent failure |
| `kb/architecture/ddb_failure_modes.md` | DuckDB-specific failures: wrong DB routed, dialect mismatch, schema mismatch, wrong MCP tool | Any query involving DuckDB |
| `kb/architecture/agent_probing_strategy.md` | Five probe types; probe-to-failure-category mapping for adversarial probe library design | Designing or reviewing probes/probes.md |

---

## Domain Documents
*Load these before querying any specific dataset.*

| File | What it answers | Load when |
|------|----------------|-----------|
| `kb/domain/yelp_schema.md` | Confirmed PostgreSQL tables, MongoDB collections, known join key mismatches, unstructured fields | Any query against the Yelp dataset |
| `kb/domain/join_keys_glossary.md` | All confirmed join key format mismatches across datasets; resolver rules | Any cross-database join |
| `kb/domain/unstructured_fields_inventory.md` | Which fields require extraction before aggregation; extraction patterns | Any query involving free-text fields |
| `kb/domain/domain_terms.md` | Correct definitions of business terms not in any schema (active, churn, high-rated, fiscal quarter) | Any query using a business term |
| `kb/domain/domain_knowledge.md` | **Layer 2 context file loaded by ContextManager.** Consolidates: domain terms, MongoDB attribute parsing rules, description field parsing, date parsing rules, all 12 dataset DB type map, live join resolution note | Loaded automatically at every session start by ContextManager |
| `kb/domain/yelp_field_map.md` | Source-of-truth field map for every Yelp concept: rating, review_count, state/city, categories, WiFi, parking, credit card, business name — with explicit anti-patterns per concept | Any Yelp query; before generating any query against Yelp data |
| `kb/domain/yelp_join_contract.md` | Canonical join key mapping (businessid_N ↔ businessref_N), normalization rules, good join vs bad join examples for both directions | Any Yelp cross-database join |
| `kb/domain/yelp_query_skeletons.md` | Per-query logic skeletons for Q1–Q7: required DB path, MongoDB stage goals, DuckDB aggregation goals, expected intermediate output shape | Any of the 7 Yelp benchmark queries |
| `kb/domain/yelp_antipatterns.md` | 15-entry wrong-pattern → correct-pattern table for all recurring Yelp failure modes (AP-01 through AP-15) | Diagnosing a wrong Yelp answer or reviewing a generated query |

---

## Evaluation Documents
*Load these before running any benchmark evaluation.*

| File | What it answers | Load when |
|------|----------------|-----------|
| `kb/evaluation/dab_read.md` | pass@1 definition, 5-trial minimum, 54-query set, GitHub PR submission format | Before any evaluation run |
| `kb/evaluation/ddb_read.md` | DuckDB-specific evaluation: routing requirement, float tolerance ±0.01, result ordering | Any evaluation query involving DuckDB |
| `kb/evaluation/scoring_method.md` | Failure category → probe design rules → query trace signals → fix directions | Diagnosing why score is not improving |

---

## Corrections Log
*Always load at session start after architecture documents.*

| File | What it answers | Load when |
|------|----------------|-----------|
| `kb/corrections/corrections_log.md` | Every observed agent failure, its diagnosis, the fix applied, and post-fix score | Session start; after every observed failure |

---

## Loading Priority Order

When context window space is limited, load in this order and stop when
the relevant documents are loaded:

```
1. kb/corrections/corrections_log.md        ← always load first
2. kb/domain/domain_terms.md                ← always load second
3. kb/domain/join_keys_glossary.md          ← always load third
4. [dataset-specific schema doc]            ← load for current dataset
5. [architecture doc for current problem]   ← load if failure diagnosis needed
6. [evaluation doc]                         ← load only during eval runs
```

---

## KB Health Status

| Subdirectory | Documents | Last injection test | Status |
|-------------|-----------|--------------------| -------|
| architecture | 8 | 2026-04-09 | ✅ All passing |
| domain | 9 | 2026-04-14 | ✅ All passing (yelp_field_map, yelp_join_contract, yelp_query_skeletons, yelp_antipatterns added) |
| evaluation | 3 | 2026-04-08 | ✅ All passing |
| corrections | 1 | 2026-04-08 | ✅ Active |

**Injection test question for this file:** What is the correct loading order
when context window space is limited?

**Expected answer:** (1) corrections_log.md, (2) domain_terms.md,
(3) join_keys_glossary.md, (4) dataset-specific schema doc,
(5) architecture doc if needed, (6) evaluation doc only during eval runs.