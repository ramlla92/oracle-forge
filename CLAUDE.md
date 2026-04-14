# Oracle Forge — Claude Code Context

## What this project is
A production-grade data analytics agent (The Oracle Forge) built for the TRP1 FDE Programme, Weeks 8-9 sprint. The agent answers natural language questions by querying across 4 database types (PostgreSQL, MongoDB, SQLite, DuckDB) using the UC Berkeley DataAgentBench (DAB) benchmark.

## Sprint dates
- **Today:** Day 3 of 10 (April 9, 2026)
- **Interim submission:** Tuesday April 14, 21:00 UTC — agent must be running on server
- **Final submission:** Saturday April 18, 21:00 UTC

## Roles
- **Driver 2 (you):** Agent Logic & Context Engineering — owns all files in `agent/`, prompts, context layers, self-correction, AGENT.md
- **Driver 1 (currently out):** Infrastructure — owns DB connections, MCP Toolbox, eval harness runner, sandbox. Driver 2 is covering.
- **Intelligence Officers:** Built `kb/`, `utils/`, `probes/` structure. Their PR is merged.
- **Signal Corps:** Owns `signal/`

## Current setup
- Developing on the **VPS** (not local machine)
- Using **local PostgreSQL and MongoDB** on the VPS until Driver 1 returns
- Tailscale access available
- `.env` file needed with: `POSTGRES_PASSWORD`, `MONGO_PASSWORD`, `ANTHROPIC_API_KEY`

## What the Intelligence Officers built (already in repo)
- `kb/` — full structure with architecture docs, domain terms, corrections log, schema overview
- `utils/schema_introspector.py` — stub implementations, needs real DB connections wired in
- `utils/join_key_resolver.py` — cross-DB join key normalizer
- `utils/multi_pass_retrieval.py` — multi-pass retrieval helper
- `mcp/tools.yaml` — full tool definitions with `<PLACEHOLDER>` connection strings
- `probes/probes.md` — adversarial probe library
- `kb/corrections/corrections_log.md` — corrections log with table format (COR-001 already populated)

## IO requests (already assessed, decisions made)
1. **"Replace tools.yaml placeholders"** → Driver 2 is covering this on VPS using local Postgres + Mongo
2. **"Run schema_introspector.py and drop output"** → Need to implement real DB connections in the stubs first, then run it and share output with IOs
3. **"Add to corrections_log.md after every failure, don't batch"** → Adopted, already in plan

## What needs to be built (Driver 2 owns all of these)

### Not started yet — build in this order:
1. `agent/models.py` — Pydantic data contracts (QueryRequest, SubQuery, QueryTrace, AgentResponse)
2. `agent/prompt_library.py` — All LLM prompts (intent_analysis, nl_to_sql, nl_to_mongodb, self_correct, synthesize_response, text_extraction)
3. `agent/context_manager.py` — Loads 3 context layers (AGENT.md, domain KB, corrections log) within token budget. Has append_correction() for self-learning loop
4. `agent/self_corrector.py` — 4-type failure diagnosis (syntax_error, wrong_table, join_key_format, domain_knowledge_gap) + retry up to 3x
5. `agent/response_synthesizer.py` — Merges DB results → human-readable answer, extracts from unstructured text
6. `agent/agent_core.py` — Main orchestration loop: analyze_intent → decompose_query → execute → synthesize → log
7. `agent/AGENT.md` — Master context file (Context Layer 1): role, tools, real DB schemas, behavioral rules
8. `agent/database_router.py` — (Driver 1 file, covering) Routes queries to correct DB type
9. `agent/query_executor.py` — (Driver 1 file, covering) Calls MCP Toolbox, handles execution errors
10. `agent/state_manager.py` — (Driver 1 file, covering) Conversation history with token-based truncation
11. `eval/run_query.py` — Single-query test runner
12. `eval/run_benchmark.py` — Full DAB benchmark runner (54 queries, 5 trials)
13. `eval/score.py` — Computes pass@1 from results JSON
14. `eval/score_log.md` — Score progression table (baseline → interim → final)
15. `sandbox/sandbox_server.py` — Code execution sandbox (FastAPI, port 8080)
16. `utils/schema_introspector.py` — Wire real DB connections into the existing stubs
17. `mcp/tools.yaml` — Replace `<PLACEHOLDER>` values with local VPS connection strings

## Architecture

```
User question
    ↓
AgentCore.run()
    ↓
ContextManager.get_full_context()   ← Layer 1 (AGENT.md schema)
                                     ← Layer 2 (domain KB)
                                     ← Layer 3 (corrections log)
    ↓
analyze_intent() → LLM → {target_databases, requires_join}
    ↓
decompose_query() → [SubQuery(db_type, query, intent), ...]
    ↓
For each SubQuery:
    QueryExecutor → MCP Toolbox → DB result
    On failure: SelfCorrector.correct() → diagnose → retry (max 3)
    ↓
DatabaseRouter merges results (join_key_resolver for format mismatches)
    ↓
ResponseSynthesizer.synthesize() → answer + query_trace
    ↓
AgentCore._log_run() → eval/run_logs/<timestamp>.json
```

## MCP tool names (exact strings, agent matches on these)
- `postgres_query` — PostgreSQL
- `mongo_aggregate` — MongoDB aggregation
- `mongo_find` — MongoDB simple find
- `sqlite_query` — SQLite
- `duckdb_query` — DuckDB
- `cross_db_merge` — cross-database result merge

## Key file references
- Full sprint plan: `planning/sprint_plan_driver2.md`
- Corrections log: `kb/corrections/corrections_log.md` (add a row after EVERY failure)
- Domain KB: `kb/domain/domain_knowledge.md`
- Schema overview: `kb/domain/schema_overview.md`
- Join key glossary: `kb/domain/join_keys_glossary.md`
- Known failure modes: `kb/architecture/dab_failure_modes.md`
- Self-correction architecture: `kb/architecture/self_correction_loop.md`

## Grading weights (what matters most)
| Deliverable | Weight |
|-------------|--------|
| Running agent on shared server | 25% |
| DAB benchmark PR with score | 20% |
| 3 context layers implemented | 20% |
| Eval harness with score log | 10% |
| Adversarial probes (15+, 3+ categories) | 10% |

## Environment setup on VPS
```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Create .env (never commit this)
# OPENROUTER_API_KEY=...   ← using OpenRouter (OpenAI-compatible), not Anthropic directly
# POSTGRES_PASSWORD=...
# POSTGRES_USER=...
# POSTGRES_HOST=127.0.0.1
# POSTGRES_DB=yelp
# MONGO_HOST=127.0.0.1
# MONGO_PASSWORD=...
# MONGO_USER=...

# 3. Load DAB datasets (clone DAB repo separately)
git clone https://github.com/ucbepic/DataAgentBench.git
cd DataAgentBench && bash setup/load_postgres.sh

# 4. Start MCP Toolbox
./toolbox --config mcp/tools.yaml

# 5. Verify tools
curl http://localhost:5000/v1/tools | python3 -m json.tool | grep name
```
