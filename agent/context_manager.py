import os
from datetime import datetime
from pathlib import Path
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

    def get_schema_for_db(self, db_type: str, dataset: str = "") -> str:
        """Extract schema from DataAgentBench hints when possible, else AGENT.md."""
        dataset_schema = self._load_dataset_schema(db_type, dataset)
        if dataset_schema:
            return dataset_schema

        content = self._load_layer1_schema()
        heading_map = {
            "mongodb":               "### MongoDB",
            "duckdb":                "### DuckDB",
            "postgresql":            "### PostgreSQL",
            "postgresql_bookreview": "### PostgreSQL",
            "sqlite":                "### SQLite",
            "github_repos_metadata":  "### GITHUB_REPOS — metadata database",
            "github_repos_artifacts": "### GITHUB_REPOS — artifacts database",
        }
        heading = heading_map.get(db_type)
        if not heading:
            return content
        start = content.find(heading)
        if start == -1:
            return content
        next_h3 = content.find("\n### ", start + len(heading))
        next_h2 = content.find("\n## ", start + 1)
        candidates = [p for p in (next_h3, next_h2) if p != -1]
        end = min(candidates) if candidates else len(content)
        return content[start:end].strip()

    def _load_dataset_schema(self, db_type: str, dataset: str) -> str:
        """Load dataset-native schema from DataAgentBench when available."""
        ds = (dataset or "").strip()
        if not ds:
            return ""

        dab_root = Path(os.getenv("DAB_ROOT", str(Path.home() / "DataAgentBench")))
        candidates = [
            dab_root / f"query_{ds}" / "db_description_withhint.txt",
            dab_root / f"query_{ds.upper()}" / "db_description_withhint.txt",
            dab_root / f"query_{ds.lower()}" / "db_description_withhint.txt",
            dab_root / f"query_{ds}" / "db_description.txt",
            dab_root / f"query_{ds.upper()}" / "db_description.txt",
            dab_root / f"query_{ds.lower()}" / "db_description.txt",
        ]
        description_path = next((p for p in candidates if p.exists()), None)
        if not description_path:
            return ""

        try:
            full_description = description_path.read_text()
        except OSError:
            return ""

        section = self._pick_db_section(full_description, db_type)
        db_hint = "PostgreSQL" if db_type == "postgresql" else db_type.upper()
        return f"### {db_hint} (DataAgentBench {ds})\n{section}"

    def _pick_db_section(self, description: str, db_type: str) -> str:
        """Return only the section relevant to the target database type."""
        lines = description.splitlines()
        sections: list[list[str]] = []
        current: list[str] = []

        def _is_section_header(line: str) -> bool:
            s = line.strip()
            return len(s) > 2 and s[0].isdigit() and s[1] == "." and s[2] == " "

        for line in lines:
            if _is_section_header(line):
                if current:
                    sections.append(current)
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append(current)

        needle = "postgresql" if db_type == "postgresql" else db_type
        for sec in sections:
            block = "\n".join(sec)
            if needle in block.lower():
                return block
        return description

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
