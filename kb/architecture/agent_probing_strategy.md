# AI Agent Internals Probing Strategy

Here is how this works.

This document summarises the five probe types from the AI Agents Internal Probing Strategy (Yabebal Fantaye, April 2026). Use these probes to study how Oracle Forge handles context, memory, and failure — and to design the adversarial probe library in `probes/probes.md`.

**The core method.** You cannot trust an AI agent's self-report about how it works. The only reliable way to study agent internals is to design prompts the agent cannot answer correctly without revealing something true about its mechanics. Run the same probe on multiple systems and compare — differences are diagnostic.

---

## The Five Probe Types

**Probe 1 — Raw Data Dump.** Forces the agent to expose whether it has active retrieval tools or only a pre-loaded memory summary. Ask the agent to output raw structured records before synthesising. Check: are timestamps real or inferred? Does it acknowledge retrieval limits or pretend to have complete access?

**Probe 2 — Behavioral Signal Retrieval.** Tests whether the agent can retrieve specific behavioral events (corrections, pushbacks) rather than just topics. A vocabulary-indexed retrieval system will miss corrections phrased as intellectual disagreement rather than explicit "you were wrong." Fix: use multiple retrieval passes with different vocabulary.

**Probe 3 — Provenance Test.** Determines whether the agent can distinguish facts from conversation history versus facts from user-provided documents. Current systems cannot — any fact provided in a document eventually becomes indistinguishable from an observed memory. Implication for Oracle Forge: provenance tagging must be implemented at the KB ingestion layer, not delegated to the LLM.

**Probe 4 — Boundary Test.** Exposes how the agent handles the edge of its retrieval capability. A well-designed agent fails gracefully ("I cannot retrieve that far back"). A poorly calibrated agent confabulates plausible-sounding results with false confidence. This is the most important reliability signal.

**Probe 5 — Architecture Disclosure.** Gets the agent to map its own internal tool stack. Ask it to explain exactly which tools it called, in what order, and why. Check whether the self-description matches the observable output. Inconsistency between claimed and observed behavior is the most valuable finding.

---

## Applying This to Oracle Forge

The adversarial probe library (`probes/probes.md`) must cover at least 3 of DAB's 4 failure categories with 15+ probes. Design each probe using the probe type that best exposes the target failure:

| DAB Failure Category | Best Probe Type | What to look for |
|---|---|---|
| Multi-database routing failure | Probe 5 (Architecture Disclosure) | Does the trace show both databases were called? |
| Ill-formatted join key mismatch | Probe 1 (Raw Data Dump) | Does the agent expose the raw key values before joining? |
| Unstructured text extraction failure | Probe 2 (Behavioral Signal) | Does the agent skip extraction and return raw text? |
| Domain knowledge gap | Probe 4 (Boundary Test) | Does the agent flag ambiguity or silently use a proxy? |

**The comparative method for Oracle Forge.** Run the same probe against the agent before and after adding a KB document. If the score improves, the document is doing its job. If it does not, the document is either not being loaded or is too vague to change behavior.

---

**Injection test question:** Which probe type is best suited to detecting whether Oracle Forge silently uses a naive proxy definition for a domain term, and what signal confirms the failure?

**Expected answer:** Probe 4 (Boundary Test) — it exposes how the agent handles ambiguity at the edge of its knowledge. The failure signal is that the agent returns a numerically plausible but wrong answer without flagging the ambiguous term, confirming it used a proxy definition rather than consulting `kb/domain/domain_terms.md`.
