"""
join_key_resolver.py
--------------------
Utility for resolving ill-formatted join key mismatches across heterogeneous
databases in the Oracle Forge data agent.

DAB Failure Category addressed: Ill-formatted join key mismatch.

Problem: Entity references (e.g. customer IDs) are formatted differently
across database systems. For example, a customer ID stored as integer 12345
in PostgreSQL may appear as "USR-12345" or "CUST-00123" in MongoDB.

Usage:
    from utils.join_key_resolver import resolve_join_key

    pg_id = 12345
    mongo_id = resolve_join_key(pg_id, source_db="postgresql", target_db="mongodb")
    # Returns: "USR-12345"  (if that is the confirmed format for this dataset)
"""

import re
from typing import Union


# Registry of known format rules per database pair.
# Key: (source_db, target_db) tuple.
# Value: dict with prefix and optional zero-padding width.
# Drivers: populate this registry as new mismatches are discovered.
# Document every entry in kb/domain/yelp_schema.md.
FORMAT_REGISTRY: dict = {
    # Yelp dataset — CONFIRMED 2026-04-11 from schema_introspector.py against live data.
    # MongoDB business.business_id = "businessid_N" → DuckDB review/tip.business_ref = "businessref_N"
    # The numeric suffix N is identical. Only the prefix differs.
    # NOTE: The agent also resolves this inline in agent_core._extract_business_refs().
    # This registry is for manual use, testing, and future datasets.
    ("mongodb_business", "duckdb_review"): {
        "source_prefix": "businessid_",
        "target_prefix": "businessref_",
        "pad_width": 0,
    },
    ("duckdb_review", "mongodb_business"): {
        "source_prefix": "businessref_",
        "target_prefix": "businessid_",
        "pad_width": 0,
    },
    # bookreview dataset (PostgreSQL + SQLite) — prefix pattern TBC after dataset load
    # ("postgresql_books", "sqlite_review"): { ... },
}


def resolve_join_key(
    value: Union[int, str],
    source_db: str,
    target_db: str,
    dataset: str = "yelp",
) -> Union[str, int, None]:
    """
    Convert a join key value from source_db format to target_db format.

    Args:
        value:      The raw key value as it appears in source_db.
        source_db:  Name of the source database system.
                    One of: "postgresql", "mongodb", "sqlite", "duckdb".
        target_db:  Name of the target database system.
        dataset:    Dataset name (for future per-dataset rule overrides).

    Returns:
        The key value reformatted for target_db, or None if no rule is found.
        Logs a warning if the conversion rule is not registered.

    Raises:
        ValueError: If value cannot be parsed according to the registered rule.
    """
    rule = FORMAT_REGISTRY.get((source_db.lower(), target_db.lower()))

    if rule is None:
        print(
            f"[join_key_resolver] WARNING: No format rule registered for "
            f"{source_db} → {target_db} (dataset={dataset}). "
            f"Add rule to FORMAT_REGISTRY and document in kb/domain/."
        )
        return None

    source_prefix = rule.get("source_prefix", "")
    target_prefix = rule.get("target_prefix", "")
    pad = rule.get("pad_width", 0)

    str_val = str(value)
    suffix = str_val[len(source_prefix):] if str_val.startswith(source_prefix) else re.sub(r"\D", "", str_val)
    if pad:
        suffix = suffix.zfill(pad)
    return f"{target_prefix}{suffix}"


# ---------------------------------------------------------------------------
# Smoke test — run this file directly to verify basic behaviour
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # MongoDB businessid_N → DuckDB businessref_N (confirmed Yelp format)
    result = resolve_join_key("businessid_49", "mongodb_business", "duckdb_review")
    assert result == "businessref_49", f"Expected 'businessref_49', got {result!r}"

    # DuckDB businessref_N → MongoDB businessid_N (reverse)
    result = resolve_join_key("businessref_34", "duckdb_review", "mongodb_business")
    assert result == "businessid_34", f"Expected 'businessid_34', got {result!r}"

    # Unknown pair returns None
    result = resolve_join_key("userid_99", "duckdb_user", "mongodb_business")
    assert result is None

    print("join_key_resolver: all smoke tests passed.")