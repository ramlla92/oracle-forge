# Oracle Forge Agent — Memory Index
## Load this file at the start of every session.

> This is the MEMORY.md equivalent for Oracle Forge.
> It tells you what knowledge exists and when to load each file.
> Do not load all files at once. Load only what the current query requires.

---

## Always Load (Every Session)

| File | What it contains |
|---|---|
| kb/corrections/corrections_log.md | Past failures and their fixes. Read this first. |
| kb/domain/schema_overview.md | All 12 DAB datasets, DB types, table names, key fields |

---

## Load When Query Involves Cross-Database Join

| File | When to load |
|---|---|
| kb/domain/join_keys_glossary.md | Any query joining data across two databases |

---

## Load When Query Uses Business Terminology

| File | When to load |
|---|---|
| kb/domain/domain_terms.md | Query mentions: volatility, handle time, BANT, churn, active customer, ETF |

---

## Load When Query Requires Text Extraction

| File | When to load |
|---|---|
| kb/domain/unstructured_fields_inventory.md | Query requires extracting values from free-text fields |

---

## Load When Query Involves DuckDB

| File | When to load |
|---|---|
| kb/architecture/ddb_failure_modes.md | Any query routing to DuckDB or involving analytical SQL |

---

## Load When Debugging a Failure

| File | When to load |
|---|---|
| kb/architecture/self_correction_loop.md | Agent produced wrong result, need to diagnose |
| kb/architecture/dab_failure_modes.md | Need to classify failure type (FM1/FM2/FM3/FM4) |

---

## Architecture Reference (Load Once, Cache)

| File | What it contains |
|---|---|
| kb/architecture/claude_code_memory.md | Three-layer memory system, Oracle Forge mapping |
| kb/architecture/openai_data_agent_context.md | Six-layer context, table enrichment, self-learning loop |
| kb/architecture/tool_scoping_and_parallelism.md | Parallel execution rules, MCP Toolbox pattern, minimum tool set |
| kb/architecture/autodream_consolidation.md | When and how to consolidate session transcripts into KB entries |
| kb/architecture/agent_probing_strategy.md | Five probe types for adversarial probe library design; probe-to-failure-category mapping |

---

## Critical Rules (Always Active)

1. After every cross-database join: check row count. Zero rows = key format mismatch.
2. For patents dataset: use dateutil.parser for dates, NOT regex.
3. For crmarenapro: TRIM() all ID fields before joining (25% have trailing spaces).
4. For bookreview: strip bid_/bref_ prefixes before joining book_id to purchase_id.
5. For stockmarket/stockindex: use adj_close, not close, for price comparisons.
6. Word boundaries in regex: use \bWORD\b not WORD (MALE matches inside FEMALE).
7. Run queries to different databases in parallel, not sequentially.
8. Spend ~20% of tool calls on exploration (list_db, sample queries) before analytical queries.
