# CHANGELOG — kb/architecture/

All changes to architecture knowledge base documents are recorded here.
Format: `[DATE] | [DOCUMENT] | [CHANGE TYPE] | [WHAT CHANGED] | [REASON]`
Change types: ADDED | UPDATED | REMOVED | INJECTION-TEST-RESULT

Maintained by: Intelligence Officers
Reviewed at: every mob session

---

## 2026-04-08

| Date | Document | Change Type | What Changed | Reason |
|------|----------|-------------|--------------|--------|
| 2026-04-08 | `claude_code_memory.md` | ADDED | Initial document created. Covers three-layer MEMORY.md architecture (index → topic files → session transcripts), injection test added. | Required KB v1 deliverable before Drivers write first agent code. |
| 2026-04-08 | `openai_context_layers.md` | ADDED | Initial document created. Covers all six context layers, identifies Layer 2 (table enrichment) as hardest sub-problem, injection test added. | Required KB v1 deliverable. |
| 2026-04-08 | `autodream_consolidation.md` | ADDED | Initial document created. Covers consolidation trigger conditions, three entry types (facts, corrections, patterns), link to corrections log. | Required KB v1 deliverable. |
| 2026-04-08 | `tool_scoping.md` | ADDED | Initial document created. Covers Claude Code 40+ narrow-tool philosophy, tool description quality test, minimum tool set for Oracle Forge. | Required KB v1 deliverable. Needed before Drivers configure tools.yaml. |
| 2026-04-08 | `self_correction_loop.md` | ADDED | Initial document created. Covers four-step loop (execute → diagnose → recover → log), four failure types and recovery actions, harness integration note. | Required KB v1 deliverable. |
| 2026-04-08 | `dab_failure_modes.md` | ADDED | Initial document created. Covers all four DAB failure categories with detection signals and fix directions. | Required KB v1 deliverable. Must exist before first probe is run. |
| 2026-04-08 | `ddb_failure_modes.md` | ADDED | Initial document created. Covers four DuckDB-specific failure modes: wrong DB routed, dialect mismatch, schema assumption mismatch, wrong MCP tool called. | Required KB v1 deliverable. DuckDB is one of four DAB database types. |

---

## Instructions for Future Entries

- Add a row every time any document in this directory is created, updated, or removed.
- If an injection test fails after an agent update, add an INJECTION-TEST-RESULT row describing what changed and how the document was revised.
- If a document becomes outdated because the agent or database changed, mark it REMOVED and explain why — do not silently delete without a log entry.
- Growth without removal is noise. If a document fails its injection test twice in a row, remove it and log the removal here.

## 2026-04-09

| Date | Document | Change Type | What Changed | Reason |
|------|----------|-------------|--------------|--------|
| 2026-04-09 | `openai_context_layers.md` | REMOVED | Deleted. Duplicate of `openai_data_agent_context.md`. Unique content (Layer 6 retrieved examples, minimum 3-layer requirement for Oracle Forge) merged into `openai_data_agent_context.md` before deletion. | Duplicate files cause agent confusion — two documents covering the same topic with different wording produce inconsistent answers on injection tests. |
| 2026-04-09 | `openai_data_agent_context.md` | UPDATED | Added Layer 6 (retrieved examples) and "Minimum Requirement for Oracle Forge" section (3 mandatory layers with their KB file mappings). Merged from deleted `openai_context_layers.md`. Fixed Layer 4 Oracle Forge equivalent reference from `join_key_glossary.md` to `join_keys_glossary.md`. | Consolidation of duplicate. Reference fix prevents agent from loading a non-existent file. |
| 2026-04-09 | `tool_scoping.md` | REMOVED | Deleted. Duplicate of `tool_scoping_and_parallelism.md`. Unique content (minimum tool set with specific tool names, tool description quality test) merged into `tool_scoping_and_parallelism.md` before deletion. | Same reason as above — duplicate files are noise. |
| 2026-04-09 | `tool_scoping_and_parallelism.md` | UPDATED | Added "Minimum Tool Set for Oracle Forge tools.yaml" section with the 5 required tool names and the tool description quality test. Merged from deleted `tool_scoping.md`. | Consolidation of duplicate. Drivers now have the complete tool configuration guidance in one file. |
| 2026-04-09 | `autodream_consolidation.md` | INJECTION-TEST-RESULT | Injection test Q: "When does autoDream consolidation trigger, and what three types of entries does it extract?" Expected: session end / 70%+ context / manual; facts learned, corrections received, successful patterns. Status: PASS — 2026-04-09 | Document was present but had no CHANGELOG injection test record. Added retroactively. |
| 2026-04-09 | `ddb_failure_modes.md` | INJECTION-TEST-RESULT | Injection test Q: "A 30-day rolling average query gets a syntax error; trace shows postgres_query was called. Which failure mode and fix?" Expected: Failure Mode 4 — wrong MCP tool called; add routing rule to AGENT.md, verify duckdb_query tool description in tools.yaml. Status: PASS — 2026-04-09 | Document was present but had no CHANGELOG injection test record. Added retroactively. |

## 2026-04-09 (second batch)

| Date | Document | Change Type | What Changed | Reason |
|------|----------|-------------|--------------|--------|
| 2026-04-09 | `claude_code_memory.md` | UPDATED | Replaced deep source-code analysis document with a focused, injectable document covering only the three-layer memory system and Oracle Forge mapping. Previous version violated Karpathy method (too long, wrong format, covered worktree isolation and API retry logic not needed by the agent). | KB documents must be injectable — paste into fresh context and get correct answers. The previous version was not injectable; it was a research artifact. |
| 2026-04-09 | `claude_code_memory.md` | INJECTION-TEST-RESULT | Injection test Q: "What is the role of MEMORY.md in Claude Code's three-layer memory system, and what is the Oracle Forge equivalent?" Expected: pointer-only index file, loaded every session, Oracle Forge equivalents are kb/MEMORY.md and kb/AGENT.md. Status: PASS — 2026-04-09 | New document verified before commit. |
| 2026-04-09 | `openai_data_agent_context.md` | UPDATED | Fixed Layer 4 Oracle Forge equivalent — removed reference to non-existent `kb/domain/query_patterns.md`, replaced with `kb/corrections/corrections_log.md` as the correct equivalent for discovered query patterns. | Broken file reference would cause agent to attempt loading a file that does not exist. |
| 2026-04-09 | `agent_probing_strategy.md` | ADDED | New document created. Covers five probe types from AI Agents Internal Probing Strategy (Fantaye, April 2026), probe-to-DAB-failure-category mapping, and the comparative method for measuring KB document effectiveness. | Challenge requires key findings from all four study sources in the KB. The probing strategy document was the only source not represented. Required before adversarial probe library is designed. |
| 2026-04-09 | `agent_probing_strategy.md` | INJECTION-TEST-RESULT | Injection test Q: "Which probe type detects silent proxy definition use for a domain term, and what signal confirms failure?" Expected: Probe 4 (Boundary Test); signal is numerically plausible but wrong answer with no ambiguity flag. Status: PASS — 2026-04-09 | Verified before commit. |
