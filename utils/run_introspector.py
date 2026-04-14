"""
Run schema introspection against loaded datasets and write
a structured markdown report to utils/schema_output.md.

Usage:
    python utils/run_introspector.py

Output:
    utils/schema_output.md  — share this file with Intelligence Officers
"""
import os
import sys
from datetime import datetime

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.schema_introspector import introspect_all, format_for_kb

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_output.md")

connections = [
    {
        "db_type": "mongodb",
        "name": "yelp_businessinfo",
        "params": {"uri": "mongodb://127.0.0.1:27017", "database": "yelp_db"},
    },
    {
        "db_type": "duckdb",
        "name": "yelp_user",
        "params": {"db_path": "db/yelp_user.db"},
    },
]

print("Running schema introspection...")
result = introspect_all(connections)

lines = []
lines.append("# Schema Introspector Output")
lines.append(f"\n**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
lines.append(f"**Datasets:** {', '.join(c['name'] for c in connections)}\n")
lines.append("---\n")
lines.append(format_for_kb(result))

lines.append("\n---")
lines.append("\n*Share this file with Intelligence Officers to update kb/domain/yelp_schema.md*")

output = "\n".join(lines)

with open(OUTPUT_PATH, "w") as f:
    f.write(output)

print(f"Done. Output written to: {OUTPUT_PATH}")
print(f"  Databases introspected : {len(result['databases'])}")
print(f"  Join key hints found   : {len(result['join_key_hints'])}")
