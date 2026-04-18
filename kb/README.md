# kb/ — LLM Knowledge Base

The Oracle Forge knowledge base. Three context layers injected by `agent/context_manager.py` at each session start. Built using the Karpathy method: minimal, precise documents injected directly into the LLM context window.

Every document is verified by an injection test before committing (see `injection_tests.md` in each subdirectory).

## Structure

| Directory | Layer | Contents | Token Budget |
|-----------|-------|----------|-------------|
| `architecture/` | v1 — Architecture | Claude Code memory system, OpenAI 6-layer context design, self-correction loop, failure mode catalogue | 2,000 |
| `domain/` | v2 — Domain | Dataset schemas, join key contracts, field maps, query patterns, anti-patterns, domain term definitions | 3,000 |
| `evaluation/` | v3 (scoring) | DAB scoring method, pass@1 definition, submission format | 500 |
| `corrections/` | v3 (corrections) | 32 structured failure entries — query that failed, root cause, fix applied, post-fix score | 2,500 |

## How Context Layers Are Injected

```python
# agent/context_manager.py
def get_full_context(self) -> str:
    layer1 = self._load_agent_md()          # agent/AGENT.md
    layer2 = self._load_domain_kb()         # kb/domain/domain_knowledge.md + dataset-specific docs
    layer3 = self._load_corrections_log()   # kb/corrections/corrections_log.md
    return self._assemble_within_budget([layer1, layer2, layer3], max_tokens=8000)
```

## Document Verification Standard

Each KB subdirectory has an `injection_tests.md` recording:
1. A test question whose correct answer requires the document's content
2. The expected answer
3. Whether the test passed (date of verification)

Documents are only committed after passing their injection test.

## Extra Files at Root Level

| File | Purpose |
|------|---------|
| `AGENT.md` | Yelp-specific agent context variant (dataset-scoped AGENT.md) |
| `AGENT_GITHUB_REPOS.md` | GITHUB_REPOS-specific agent context variant |
| `MEMORY.md` | Claude Code memory index (pointers to per-topic memory files) |
