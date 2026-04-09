# Claude Code Three-Layer Memory System

Here is how this works.

Claude Code uses a three-layer memory architecture to persist knowledge across sessions without loading everything into context at once. Oracle Forge replicates this pattern using the KB file structure.

**Layer 1 — MEMORY.md (The Index).** A single file loaded at the start of every session. It is NOT a content file — it is a pointer file. It lists what knowledge exists and where to find it. The agent reads this first, then decides which topic files to load for the current query. Maximum 200 lines / 25KB. Overflow is truncated. Oracle Forge equivalent: `kb/MEMORY.md` and `kb/AGENT.md` loaded at session start.

**Layer 2 — Topic Files (On-Demand Knowledge).** Individual markdown files, each covering exactly one domain. Loaded only when the agent determines it needs that knowledge for the current query. Each file must be self-contained: paste it into a fresh LLM context with no other information and the LLM must answer questions about that topic correctly from the file alone. If it cannot, the file is too vague and must be rewritten. Oracle Forge equivalents: all files in `kb/architecture/`, `kb/domain/`, `kb/evaluation/`.

**Layer 3 — Session Transcripts (Searchable History).** JSONL logs of past agent sessions stored on disk. Never loaded directly into context. Only accessed by the autoDream consolidation process, which distills them into structured topic file entries. Oracle Forge equivalent: `kb/corrections/corrections_log.md` — structured log of past failures and fixes, read at session start.

**The design rule.** The agent never loads all topic files at once. It reads the index (Layer 1), identifies which topic files are relevant to the current query, loads only those (Layer 2), and uses the corrections log (Layer 3) to avoid repeating known mistakes. This keeps context usage predictable and leaves room for query results.

**Oracle Forge mapping:**

| Claude Code Component | Oracle Forge Equivalent |
|---|---|
| MEMORY.md index file | kb/MEMORY.md + kb/AGENT.md |
| Topic files (on-demand) | kb/architecture/*.md, kb/domain/*.md, kb/evaluation/*.md |
| Session transcripts | kb/corrections/corrections_log.md |
| autoDream consolidation | kb/architecture/autodream_consolidation.md |

---

**Injection test question:** What is the role of MEMORY.md in Claude Code's three-layer memory system, and what is the Oracle Forge equivalent?

**Expected answer:** MEMORY.md is a pointer-only index file loaded at every session start. It contains one-line references to topic files — no actual content. The agent reads it first to know what knowledge exists, then loads only the relevant topic files for the current query. The Oracle Forge equivalents are `kb/MEMORY.md` and `kb/AGENT.md`.
