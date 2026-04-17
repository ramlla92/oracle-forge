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
        """Truncate from the middle, preserving Layer 1 (schema) and recent corrections."""
        char_budget = token_budget * 4
        if len(text) <= char_budget:
            return text
        half = char_budget // 2
        keep_start = min(max(half, preserve_start), char_budget)
        keep_end = char_budget - keep_start
        if keep_end <= 0:
            return text[:keep_start] + "\n...[context truncated to fit token budget]..."
        truncation_msg = "\n...[context truncated to fit token budget]...\n"
        return text[:keep_start] + truncation_msg + text[-keep_end:]

    def get_schema_for_db(self, db_type: str) -> str:
        """Extract the schema section for a specific DB type from AGENT.md."""
        content = self._load_layer1_schema()
        # Map db_type to the heading used in AGENT.md
        heading_map = {
            "mongodb":               "### MongoDB",
            "duckdb":                "### DuckDB",
            "postgresql":            "### PostgreSQL",
            "postgresql_bookreview": "### PostgreSQL",
            "postgresql_crm":        "### CRMArena Pro",
            "sqlite":                "### SQLite",
            # crmarenapro logical DB names — all point to the same CRMArena Pro section
            "core_crm":              "### CRMArena Pro",
            "sales_pipeline":        "### CRMArena Pro",
            "support":               "### CRMArena Pro",
            "products_orders":       "### CRMArena Pro",
            "activities":            "### CRMArena Pro",
            "territory":             "### CRMArena Pro",
            # DEPS_DEV_V1 logical DB names
            "package_database":      "### SQLite — deps_dev package_database",
            "project_database":      "### DuckDB — deps_dev project_database",
        }
        heading = heading_map.get(db_type)
        if not heading:
            return content
        start = content.find(heading)
        if start == -1:
            return content
        # Find the next sibling (###) or parent (##) heading after our section
        next_h3 = content.find("\n### ", start + len(heading))
        next_h2 = content.find("\n## ", start + 1)
        candidates = [p for p in (next_h3, next_h2) if p != -1]
        end = min(candidates) if candidates else len(content)
        return content[start:end].strip()

    def get_schema_for_logical_db(self, logical_name: str) -> str:
        """Return a focused schema snippet for a specific logical DB.
        For datasets where each logical DB has its own AGENT.md section (DEPS_DEV_V1),
        returns that full section. For CRM (all share one section), filters to the relevant tables.
        """
        deps_logical = {"package_database", "project_database"}
        if logical_name in deps_logical:
            return self.get_schema_for_db(logical_name)

        full_crm = self.get_schema_for_db(logical_name)
        # Extract just the line(s) for this CRM logical DB from the shared CRMArena Pro section
        lines = full_crm.split("\n")
        result = []
        in_section = False
        for line in lines:
            if line.startswith("### CRMArena") or line.startswith("**DAB root") or line.startswith("**Critical"):
                result.append(line)
                in_section = False
            elif line.startswith(f"`{logical_name}`"):
                result.append(line)
                in_section = True
            elif in_section and line.startswith("`") and not line.startswith(f"`{logical_name}`"):
                in_section = False
            elif in_section:
                result.append(line)
        return "\n".join(result) if result else full_crm
        heading = heading_map.get(db_type)
        if not heading:
            return content
        start = content.find(heading)
        if start == -1:
            return content
        # Find the next sibling (###) or parent (##) heading after our section
        next_h3 = content.find("\n### ", start + len(heading))
        next_h2 = content.find("\n## ", start + 1)
        candidates = [p for p in (next_h3, next_h2) if p != -1]
        end = min(candidates) if candidates else len(content)
        return content[start:end].strip()

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
        | ID | Date | Query | Failure Category | What Was Expected
        | What Agent Returned | Fix Applied | Post-Fix Score |
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
            existing = [line for line in content.splitlines() if line.startswith("| COR-")]
            return f"COR-{str(len(existing) + 1).zfill(3)}"
        except FileNotFoundError:
            return "COR-001"
