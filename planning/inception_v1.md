# AI-DLC Inception Document — Oracle Forge
**Team:** Falcon | **Sprint:** Weeks 8–9 | **Date:** April 9, 2026
**Status:** DRAFT — Pending team approval at mob session

## Press Release
Team Falcon's Oracle Forge is a production-grade natural language data analytics
agent that answers complex business questions across heterogeneous database systems
— PostgreSQL, MongoDB, SQLite, and DuckDB — in a single response. The agent
receives a plain-English question, routes sub-queries to the correct database
types, resolves ill-formatted join keys automatically, extracts structured facts
from free-text fields, and applies institutional domain knowledge to interpret
business terminology correctly. Oracle Forge self-corrects on execution failure
without surfacing errors to the user. Its three-layer context architecture —
schema knowledge, domain knowledge, and a self-updating corrections log —
produces measurably higher accuracy between the Week 8 baseline and the final
DataAgentBench submission.

## Honest FAQ — User

**Q: What databases can Oracle Forge query?**
A: PostgreSQL, MongoDB, SQLite, and DuckDB. It can answer questions that
require joining data across all four systems in a single response.

**Q: Will it always give the correct answer?**
A: No. It targets a pass@1 score above the current open-source baseline of
37.6% on DataAgentBench. Complex queries requiring three or more cross-database
joins, or queries using business terms not in the knowledge base, remain a
known failure category.

**Q: What does it not do?**
A: It does not write to databases. It does not learn permanently from user
corrections within a session — corrections are logged and loaded at next
session start. It does not handle real-time streaming data.

## Honest FAQ — Technical

**Q: What is the hardest part of this build?**
A: Ill-formatted join key resolution. Customer IDs stored as integers in
PostgreSQL and as "CUST-00123" strings in MongoDB require automatic detection
and format normalization before any cross-database join can succeed. The agent
must detect the mismatch, resolve it, and retry without being told explicitly.

**Q: What are the critical dependencies?**
A: Anthropic Claude API (agent LLM), Google MCP Toolbox v0.30 (database
connections), DataAgentBench (evaluation harness and datasets), PostgreSQL 17.5+,
MongoDB 8.0+, DuckDB 1.5.1, Docker (safe Python execution sandbox).

**Q: What could go wrong?**
A: MCP Toolbox connection loss mid-query returns partial answers without
signalling failure. Docker sandbox timeouts on complex Python transformations
silently terminate queries. MongoDB aggregation pipelines requiring explicit
field projection before joining with PostgreSQL results are a known failure
mode documented in our corrections log.

## Key Decisions

1. **Extend DataAgent.py rather than rewrite from scratch.**
   Reason: The scaffold correctly handles tool management, logging, and LLM
   retry logic. Our value is in context engineering and self-correction.

2. **Use Claude as the backbone LLM.**
   Reason: Claude support is already implemented in DataAgent.py, the team
   has API access, and Claude Sonnet 4.6 matches near the top of the DAB
   leaderboard.

3. **Start evaluation with DuckDB + SQLite datasets before PostgreSQL/MongoDB.**
   Reason: Five datasets are testable immediately without server dependencies,
   allowing a Week 8 baseline score before full infrastructure is available.

## Definition of Done

1. Agent runs on team server (falcon.10academy.org) and accepts natural language
   queries via the DataAgentBench run_agent.py interface.
2. Agent handles at least two DAB database types (DuckDB + SQLite minimum,
   all four as target).
3. Agent pass@1 score recorded at Week 8 baseline (minimum 5 queries,
   minimum 5 trials each).
4. All three context layers implemented and populated:
   kb/architecture/, kb/domain/, kb/corrections/
5. Evaluation harness produces a score log with at least two data points:
   Week 8 baseline and Week 9 final score.
6. Adversarial probe library contains minimum 15 probes across minimum 3
   failure categories in probes/probes.md.
7. DAB results JSON (50 runs x all queries) submitted via GitHub PR to
   ucbepic/DataAgentBench.
8. All six team members have committed to the oracle-forge repository.

## Mob Session Approval Record
**Date of approval:** _______________
**Approved by:** _______________
**Hardest question asked:** _______________
**Answer given:** _______________
