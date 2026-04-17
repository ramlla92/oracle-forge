from agent.models import SubQuery

# Maps dataset names to their DB type assignments (from DAB db_config.yaml files)
DATASET_DB_MAP = {
    "yelp":          {"businessinfo_database": "mongodb", "user_database": "duckdb"},
    "agnews":        {"articles_database": "mongodb",     "metadata_database": "sqlite"},
    "bookreview":    {"books_database": "postgresql",     "review_database": "sqlite"},
    "crmarenapro":   {"core_crm": "sqlite", "sales_pipeline": "duckdb", "support": "postgresql_crm",
                      "products_orders": "sqlite", "activities": "duckdb", "territory": "sqlite"},
    "googlelocal":   {"business_database": "postgresql",  "review_database": "sqlite"},
    "music_brainz":  {"tracks_database": "sqlite",        "sales_database": "duckdb"},
    "stockindex":    {"indexinfo_database": "sqlite",      "indextrade_database": "duckdb"},
    "stockmarket":   {"stockinfo_database": "sqlite",      "stocktrade_database": "duckdb"},
    "pancancer":     {"clinical_database": "postgresql",   "molecular_database": "duckdb"},
    "DEPS_DEV_V1":   {"package_database": "sqlite",        "project_database": "duckdb"},
    "github_repos":  {"metadata_database": "sqlite",       "artifacts_database": "duckdb"},
    "patents":       {"publication_database": "sqlite",     "CPCDefinition_database": "postgresql"},
}

# Keywords that signal which DB type a question targets
DB_TYPE_SIGNALS = {
    "mongodb": ["business", "checkin", "attributes", "hours", "description", "articles", "support"],
    "duckdb": ["review", "tip", "user", "rating", "trade", "sales", "molecular", "project"],
    "postgresql": ["books", "crm", "googlelocal", "clinical", "patent", "CPCDefinition"],
    "sqlite":     ["metadata", "package", "tracks", "stockinfo", "indexinfo", "territory"],
}


class DatabaseRouter:

    def route(self, intent: dict, dataset: str = "yelp") -> list[str]:
        """Return ordered list of DB types to query for this intent.

        Args:
            intent: Output of AgentCore.analyze_intent() — includes target_databases list.
            dataset: Active DAB dataset name.

        Returns:
            List of DB type strings e.g. ["mongodb", "duckdb"]
        """
        # Trust LLM intent if it named specific DBs
        if intent.get("target_databases"):
            return intent["target_databases"]

        # Fall back to keyword matching against the question
        question = intent.get("intent_summary", "").lower()
        matched = []
        for db_type, signals in DB_TYPE_SIGNALS.items():
            if any(sig in question for sig in signals):
                matched.append(db_type)

        # Default to all DBs for this dataset if no signal matches
        if not matched:
            db_map = DATASET_DB_MAP.get(dataset, {})
            matched = list(set(db_map.values()))

        return matched

    def requires_cross_db_merge(self, sub_queries: list[SubQuery]) -> bool:
        """True if the sub-queries span more than one DB type."""
        db_types = {sq.database_type for sq in sub_queries}
        return len(db_types) > 1
