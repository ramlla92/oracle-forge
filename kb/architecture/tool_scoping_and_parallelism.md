# Tool Scoping and Parallel Execution Pattern

> KB v1 — Architecture Layer | Oracle Forge
> Source: Claude Code architecture (learn-coding-agent repo, ~512k lines TypeScript)
> Purpose: Give the agent the tool composition and parallelism patterns used in
> production agents, so it executes DAB queries efficiently.

---

## Core Principle: One Tool, One Job

Claude Code has 40+ tools. Each does exactly one thing.
Tools are composed into pipelines, not combined into mega-tools.
This enables: parallel execution, independent retry, clear error attribution.

For Oracle Forge, the DAB tools follow the same principle:
- list_db → lists tables in one database (one job)
- query_db → executes one query against one database (one job)
- execute_python → runs one Python transformation (one job)
- return_answer → returns the final answer (one job)

Never combine: do not write one Python block that queries, transforms, and answers.
Break it into discrete steps. Each step is inspectable before proceeding.

---

## Concurrency: What Can Run in Parallel

From Claude Code: isConcurrencySafe() = true means the tool can run in parallel.

For DAB queries:
- Queries to DIFFERENT databases are concurrency-safe → run in parallel
- Queries to the SAME database are serial → run sequentially
- Python transformations on already-fetched data → run after all queries complete

Example — bookreview query requiring both databases:
```
PARALLEL:
  query_db('books_database', 'SELECT book_id, title, details FROM books_info')
  query_db('review_database', 'SELECT purchase_id, rating, review_time FROM review')

THEN (after both complete):
  execute_python(merge and compute answer)
```

Do NOT:
```
SERIAL (wrong):
  query_db('books_database', ...)  ← wait for this
  query_db('review_database', ...) ← then do this
```

The parallel pattern cuts query time roughly in half for two-database queries.
For crmarenapro (6 databases), parallel execution is critical for staying within time limits.

---

## The MCP Toolbox Pattern

Google MCP Toolbox for Databases provides the standard interface.
A single tools.yaml file defines all database connections as named logical tools.
The agent calls tools by logical name, not by connection string.

```yaml
# tools.yaml structure
sources:
  books_database:
    kind: postgres
    host: localhost
    database: bookreview_db
  review_database:
    kind: sqlite
    database: /path/to/review_query.db
```

Agent calls: query_db('books_database', 'SELECT ...')
Agent never sees: connection strings, passwords, physical paths.

This is the same pattern as Claude Code's tool abstraction:
the agent works with logical tool names, not implementation details.

---

## Minimum Tool Set for Oracle Forge tools.yaml

Each database type must have its own distinct tool — never a shared generic query tool.
This prevents DAB Failure Category 1 (multi-database routing failure).

- `postgres_query` — executes SQL against PostgreSQL databases; returns rows as JSON
- `mongo_aggregate` — executes MongoDB aggregation pipelines; returns documents as JSON
- `sqlite_query` — executes SQL against SQLite databases; returns rows as JSON
- `duckdb_query` — executes analytical SQL against DuckDB; returns columnar result as JSON
- `cross_db_merge` — merges result sets from two database tools on a specified key after format resolution

**Tool description quality test.** For each tool in `tools.yaml`, ask: if the agent reads only
this description, will it call this tool and not another for its intended query type?
If the answer is "maybe," the description is too vague. Rewrite it until the answer is
"yes, unambiguously."

---

## Sub-Agent Spawn Modes (from Claude Code)

Relevant for understanding how the Conductor/worktree pattern works:

**fork mode**: child process, fresh message history, shared file cache.
Used in Week 4 Brownfield Cartographer for parallel codebase analysis.
Oracle Forge equivalent: parallel database query sessions.

**worktree mode**: isolated git worktree + fork.
Used for running experiments without interfering with main branch.
Oracle Forge equivalent: running probe queries without affecting benchmark state.

**in-process mode**: same process, shared conversation context.
Default mode. Used for the main agent loop.

---

## Tool Execution Decision Tree for DAB Queries

```
Query arrives
    ↓
Does it require data from multiple databases?
    YES → identify all required databases → query in parallel
    NO  → query single database directly
    ↓
Does it require text extraction from unstructured fields?
    YES → check unstructured_fields_inventory.md for extraction method
          data-independent → use regex pattern from KB
          data-dependent   → use LLM extraction via execute_python
    NO  → proceed with SQL/MongoDB query result directly
    ↓
Does it require cross-database join?
    YES → check join_keys_glossary.md for key format
          normalize keys using join_key_resolver.py
          merge in execute_python
    NO  → return query result directly
    ↓
Does it require domain knowledge to interpret result?
    YES → check domain_terms.md for term definition
    NO  → return answer
```

---

## Exploration Budget: The 20% Rule

From DAB paper analysis: agents that spend ~20% of tool calls on exploration
(schema inspection, sample queries, list_db) outperform agents that spend less or more.

Less than 10% exploration: agent jumps to conclusions, misses schema details.
More than 25% exploration: agent wastes budget, runs out of iterations.

For Oracle Forge: plan for 2-3 exploratory tool calls per query before analytical calls.
- 1 list_db call per new database
- 1 sample query (SELECT * LIMIT 3) per table you haven't seen before
- Then proceed with analytical queries

Do NOT: call list_db on every database for every query.
Do NOT: skip exploration entirely and assume you know the schema.
