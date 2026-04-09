# OpenAI In-House Data Agent — Six-Layer Context Architecture

> KB v1 — Architecture Layer | Oracle Forge
> Source: openai.com/index/inside-our-in-house-data-agent (January 2026)
> Purpose: Give the agent the exact context layering pattern used by the best
> production data agent in existence, so Oracle Forge replicates it for DAB.

---

## The Scale Problem

OpenAI's data platform: 3,500+ internal users, 600 petabytes, 70,000 datasets.
The hardest sub-problem is NOT writing the query.
The hardest sub-problem is FINDING THE RIGHT TABLE.
An agent with perfect SQL skills but no table knowledge will fail.
An agent with imperfect SQL but rich context will succeed.

This is why context engineering is the bottleneck, not model capability.

---

## Layer 1: Table-Level Knowledge (The Hardest Layer)

Codex generates natural-language descriptions for every table OFFLINE before queries arrive.
Each description answers:
- What is this table?
- What is it used for?
- How does it relate to other tables?
- What are the key columns and their meanings?

Stored as a searchable index. Agent retrieves relevant tables by semantic search.
This is pre-computed, not discovered at query time.

Oracle Forge equivalent:
kb/domain/schema_overview.md — manually written descriptions for all 12 DAB datasets.
This is the most important KB v2 file. It replaces Codex table enrichment for our scale.

---

## Layer 2: Schema Layer

Raw column names, types, and sample values.
Standard schema introspection output.
Populated by running schema_introspector.py against each database.

Oracle Forge equivalent: schema_overview.md also contains this.
For each dataset: table names, column names, types, sample values.

---

## Layer 3: Organizational Context Layer

Business term definitions NOT in the schema.
Which tables are authoritative vs deprecated.
Fiscal year boundaries, status code meanings, metric definitions.
Things a new analyst would need to be told by a senior colleague.

Oracle Forge equivalent: kb/domain/domain_terms.md
Contains: intraday volatility formula, BANT qualification definition,
handle time definition, CDH1 mutation criteria, ETF vs stock classification.

---

## Layer 4: Query Pattern Layer

Known SQL patterns that work for this data.
Known patterns that FAIL (e.g., many-to-many joins that inflate counts).
Join key format mappings across databases.
Patterns discovered through trial and error, documented so they are not rediscovered.

Oracle Forge equivalent:
- kb/domain/join_keys_glossary.md → join key format mismatches
- kb/corrections/corrections_log.md → successful patterns discovered through trial and error

---

## Layer 5: Interaction Memory Layer

Corrections received from users.
Successful query patterns from past sessions.
User preferences (e.g., "always use adjusted close for volatility").
Things the agent learned from being wrong and being corrected.

Oracle Forge equivalent: kb/corrections/corrections_log.md
Format: [query that failed] → [what was wrong] → [correct approach] → [fix applied]

---

## Layer 6: Retrieved Examples (Closed-Loop Self-Correction)

At query time, semantically similar past queries with their confirmed correct answers are
injected. The agent sees "here is how a similar question was answered before."
This is the self-learning loop — the agent improves from its own history without retraining.

The mechanism that makes the agent improve without retraining.

Pattern:
1. Query arrives
2. Agent attempts answer
3. Execution fails OR intermediate result looks wrong
4. Agent diagnoses failure type
5. Agent adjusts approach and retries
6. Outcome logged to corrections log
7. Next session: agent reads corrections log and avoids the same mistake

Key check: after every cross-database join, verify row count is plausible.
Zero rows = join key format mismatch. Investigate before proceeding.
Astronomically high rows = many-to-many join. Add deduplication.

Oracle Forge implementation:
- Agent checks row counts after every join
- Agent reads corrections_log.md at session start
- Drivers log failures to corrections_log.md after every mob session
- IO compresses and maintains the log

---

## Minimum Requirement for Oracle Forge

The challenge requires three demonstrably working layers minimum:
- Layer 1 (schema/metadata) → kb/domain/schema_overview.md + kb/domain/yelp_schema.md
- Layer 3 (institutional knowledge) → kb/domain/domain_terms.md
- Layer 5 (interaction memory) → kb/corrections/corrections_log.md

All six layers are the target. Layers 1, 2, 3, 4, 5 can be implemented before the benchmark.
Layer 6 (retrieved examples) improves score between Week 8 baseline and Week 9 submission.

---

## Why This Architecture Beats Raw LLM Capability

Gemini 3 Pro (best frontier model) scores 38% pass@1 on DAB with no context engineering.
PromptQL (specialized data agent with semantic layer) scores 51% pass@1 on same queries.
The 13 percentage point gap comes entirely from context engineering, not model capability.

Our target: exceed 38% by applying all six layers to DAB's 12 datasets.
