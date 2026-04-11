from datetime import datetime
from typing import Optional


class ContextManager:

    def __init__(self, agent_md_path: str, corrections_path: str, domain_kb_path: str):
        self.agent_md_path = agent_md_path
        self.corrections_path = corrections_path
        self.domain_kb_path = domain_kb_path
        self._session_history: list[dict] = []
        self._correction_count: int = 0

    def get_full_context(self, token_budget: int = 8000) -> str:
        """Assemble all three context layers within token budget.

        Layer 1 — AGENT.md (schema + behavioral rules) — highest priority, never truncated
        Layer 2 — Domain KB (terms, fiscal conventions, status codes)
        Layer 3 — Corrections log (past failures + fixes)
        """
        layer1 = self._load_layer1_schema()
        layer2 = self._load_layer2_domain()
        layer3 = self._load_layer3_corrections()
        session = self.get_session_context()

        full = "\n\n---\n\n".join(filter(None, [layer1, layer2, layer3, session]))
        return self._fit_to_budget(full, token_budget, preserve_start=len(layer1))

    def _load_layer1_schema(self) -> str:
        try:
            with open(self.agent_md_path) as f:
                return f.read()
        except FileNotFoundError:
            return "# Agent Context\n(AGENT.md not found)"

    def _load_layer2_domain(self) -> str:
        try:
            with open(self.domain_kb_path) as f:
                return f.read()
        except FileNotFoundError:
            return "# Domain Knowledge\n(Not yet populated)"

    def _load_layer3_corrections(self) -> str:
        try:
            with open(self.corrections_path) as f:
                return f.read()
        except FileNotFoundError:
            return "# Corrections Log\n(No corrections yet)"

    def _fit_to_budget(self, text: str, token_budget: int, preserve_start: int = 0) -> str:
        """Truncate from the middle, always preserving Layer 1 (schema) and the end (recent corrections)."""
        char_budget = token_budget * 4
        if len(text) <= char_budget:
            return text
        half = char_budget // 2
        # Keep at least the preserved start block intact
        keep_start = max(half, preserve_start)
        keep_end = char_budget - keep_start
        return text[:keep_start] + "\n...[context truncated to fit token budget]...\n" + text[-keep_end:]

    def add_to_session(self, query: str, result_summary: str, correction: Optional[str] = None):
        self._session_history.append({
            "query": query,
            "result_summary": result_summary[:200],
            "correction": correction,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._session_history = self._session_history[-10:]

    def get_session_context(self) -> str:
        if not self._session_history:
            return ""
        items = [f"- {h['query']}: {h['result_summary']}" for h in self._session_history[-5:]]
        return "## Recent Session Queries\n" + "\n".join(items)

    def append_correction(self, query: str, what_went_wrong: str, correct_approach: str,
                          failure_category: str = "unknown"):
        """Write a new correction table row immediately (never batch).

        Matches the format defined in kb/corrections/corrections_log.md:
        | ID | Date | Query | Failure Category | What Was Expected | What Agent Returned | Fix Applied | Post-Fix Score |
        """
        entry_id = self._next_entry_id()
        date = str(datetime.utcnow().date())
        # Sanitize pipe chars so they don't break the table
        def clean(s: str) -> str:
            return s.replace("|", "/").replace("\n", " ").strip()

        row = (
            f"| {entry_id} | {date} | {clean(query)} | {clean(failure_category)} "
            f"| — | {clean(what_went_wrong)} | {clean(correct_approach)} | pending |\n"
        )
        with open(self.corrections_path, "a") as f:
            # Ensure we're on a new line before appending the row
            f.write("\n" + row)

    def _next_entry_id(self) -> str:
        """Count existing COR-NNN rows to derive the next ID."""
        try:
            with open(self.corrections_path) as f:
                content = f.read()
            existing = [l for l in content.splitlines() if l.startswith("| COR-")]
            return f"COR-{str(len(existing) + 1).zfill(3)}"
        except FileNotFoundError:
            return "COR-001"
