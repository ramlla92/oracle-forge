# kb/corrections/ — KB v3 (Corrections): Failure Log

Structured log of every agent failure observed during benchmark runs. Read by the agent at session start as Context Layer 3. New entries are appended after every failure — never batched.

## Files

| File | Contents |
|------|----------|
| `corrections_log.md` | 32 failure entries (COR-001 through COR-032) — each with query, failure category, expected vs actual, root cause, fix applied, post-fix score |
| `github_repos_corrections.md` | GITHUB_REPOS-specific corrections (complex join + schema mismatch patterns) |
| `injection_tests.md` | Verified test queries confirming the corrections log is correctly injected and retrieved |
| `CHANGELOG.md` | Version history — each entry corresponds to a corrections batch |

## Entry Format

Each row in `corrections_log.md` follows this structure:

```
| ID | Date | Query | Failure Category | Expected | Actual | Root Cause | Fix Applied | Post-Fix Score |
```

## Systemic Patterns

Four systemic failure patterns identified from COR-001 through COR-032:

| Pattern | Description | Affected Entries | Fix Location |
|---------|-------------|-----------------|--------------|
| A | SQL wrapped in markdown code fences | 9 queries | `prompt_library.nl_to_sql()` |
| B | MongoDB pipeline serialized as JSON string | 12 queries | `prompt_library.nl_to_mongodb()` |
| C | Agent queries non-existent DuckDB tables | 4 queries | `agent/AGENT.md` Critical Rules |
| D | Fixed `strptime` format on mixed-date fields | 6 queries | `prompt_library.nl_to_sql()` |

## How This Layer Is Used

`agent/context_manager.py` calls `append_correction()` after every failed query (up to 3 retries). The full corrections log is loaded at session start, enabling the agent to avoid previously observed failure modes before they occur.
