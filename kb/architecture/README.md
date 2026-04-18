# kb/architecture/ — KB v1: Architecture Knowledge

System design patterns for data agents — injected as Context Layer 1 (alongside AGENT.md) at session start.

## Documents

| File | Contents | Injection Test |
|------|----------|---------------|
| `claude_code_memory.md` | Claude Code three-layer MEMORY.md system and how Oracle Forge maps to it | ✓ verified |
| `openai_data_agent_context.md` | OpenAI 6-layer context design; Layer 2 (table enrichment) identified as hardest sub-problem | ✓ verified |
| `self_correction_loop.md` | 4-step self-correction loop: execute → diagnose → recover → log | ✓ verified |
| `dab_failure_modes.md` | All 4 DAB failure categories with diagnosis patterns and recovery strategies | ✓ verified |
| `ddb_failure_modes.md` | DuckDB-specific failure modes (table scope, strptime, type casting) | ✓ verified |
| `tool_scoping_and_parallelism.md` | 5-tool minimum set for Oracle Forge; parallel vs sequential tool use | ✓ verified |
| `agent_probing_strategy.md` | Five adversarial probe types; how IOs structured the probes library | ✓ verified |
| `autodream_consolidation.md` | AutoDream pattern — autonomous session memory consolidation | ✓ verified |
| `injection_tests.md` | Verified test query + expected answer for each document above | — |
| `CHANGELOG.md` | Version history for this KB layer | — |

## How This Layer Is Used

`agent/context_manager.py` loads all documents in this directory into the LLM context window at session start. Documents are ordered by relevance score from `utils/multi_pass_retrieval.py`. Token budget for this layer: 2,000 tokens.

## Verification Standard

Each document has a recorded injection test in `injection_tests.md`: a test question whose correct answer requires the document's content, with expected answer noted. Documents are committed only after passing the injection test.
