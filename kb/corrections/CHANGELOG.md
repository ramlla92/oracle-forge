# CHANGELOG — kb/corrections/

All structural changes to the corrections log are recorded here.
Note: individual failure entries are logged directly in corrections_log.md —
this CHANGELOG tracks changes to the log's structure, format, or bulk operations
(e.g. promoting entries to domain KB documents, archiving resolved entries).

Format: `[DATE] | [CHANGE TYPE] | [WHAT CHANGED] | [REASON]`
Change types: STRUCTURE-CHANGE | PROMOTED | BULK-REVIEW | FORMAT-UPDATE

Maintained by: Intelligence Officers
Reviewed at: every mob session

---

## 2026-04-08

| Date | Change Type | What Changed | Reason |
|------|-------------|--------------|--------|
| 2026-04-08 | STRUCTURE-CHANGE | `corrections_log.md` created with columns: ID, Date, Query, Failure Category, What Was Expected, What Agent Returned, Fix Applied, Post-Fix Score. Example row COR-001 added (multi-database routing failure on support ticket query). | Required KB v3 deliverable. Self-learning loop requires a structured log the agent reads at session start. |

---

## Instructions for Future Entries

**What belongs in this CHANGELOG vs corrections_log.md:**
- Individual agent failures → go directly into `corrections_log.md` (Drivers add these after every observed failure).
- Structural changes to the log format, bulk promotions of entries to domain KB docs, or periodic reviews → go here.

**Promotion process:** When a correction entry reveals a pattern (the same failure type appears 3+ times), Intelligence Officers should promote it:
1. Extract the pattern into the relevant `kb/domain/` or `kb/architecture/` document.
2. Add a PROMOTED row here referencing the COR IDs that were promoted and the destination document.
3. The original COR entries remain in `corrections_log.md` — they are never deleted.

**Bulk review:** At the end of each week, Intelligence Officers review all new COR entries and determine which should be promoted. Log the review outcome here even if no promotions occurred.

| Review Date | COR IDs Reviewed | Promoted | Destination | Notes |
|-------------|-----------------|----------|-------------|-------|
| 2026-04-08 | COR-001 | No | — | Single entry, pattern not yet established. Monitor for recurrence. |

---

## 2026-04-14 (feat/kb-v2-yelp-domain)

| Date | Change Type | What Changed | Reason |
|------|-------------|--------------|--------|
| 2026-04-14 | PROMOTED | COR-002 through COR-032 patterns promoted to `kb/domain/yelp_antipatterns.md`. Four systemic patterns (A=code fences, B=pipeline as string, C=wrong table, D=date format) now have corresponding AP entries (AP-10, AP-05, AP-10, AP-10 respectively) with correct-pattern documentation. | 32 correction entries showed 4 recurring patterns. Promoted to domain KB so agent reads the fix at session start rather than only after failure. |
| 2026-04-14 | BULK-REVIEW | Probes 016–020 added to `probes/probes.md` linking to AP-01, AP-02/03, AP-04/05, AP-06, AP-09 anti-patterns and referencing COR IDs. | Driver requested probe updates after anti-pattern table was complete. Each new probe documents the observed failure, links to the correction IDs that surfaced it, and references the fix in yelp_antipatterns.md. |
