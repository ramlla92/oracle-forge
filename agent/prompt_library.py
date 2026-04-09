import json


class PromptLibrary:

    def intent_analysis(self, question: str, available_databases: list[str]) -> str:
        return f"""Analyze this data question and determine which databases to query.
Consult the domain knowledge in your context for any ambiguous terms or fiscal/status conventions.

Question: {question}
Available databases: {', '.join(available_databases)}

Respond with valid JSON only:
{{
  "target_databases": ["postgresql", "mongodb"],
  "intent_summary": "brief description of what data is needed",
  "requires_join": true,
  "data_fields_needed": ["field1", "field2"]
}}"""

    def nl_to_sql(self, question: str, schema: str, dialect: str = "postgresql") -> str:
        return f"""Generate a {dialect.upper()} query for this question.

Schema:
{schema}

Question: {question}

Rules:
- Return only the SQL query, no explanation
- Use exact table and column names from the schema
- For {dialect}: {self._dialect_rules(dialect)}"""

    def nl_to_mongodb(self, question: str, collection_schema: str) -> str:
        return f"""Generate a MongoDB aggregation pipeline for this question.

Collection schema:
{collection_schema}

Question: {question}

Return a valid JSON array representing the aggregation pipeline stages.
Example: [{{"$match": {{"status": "active"}}}}, {{"$group": {{"_id": "$category", "count": {{"$sum": 1}}}}}}]

Return only the JSON array, no explanation."""

    def self_correct(self, question: str, failed_query: str, error: str,
                     db_type: str, schema: str, fix_strategy: str = "") -> str:
        strategy_hint = f"\nFix strategy: {fix_strategy}" if fix_strategy else ""
        return f"""A database query failed. Generate a corrected query.
Check the corrections log in your context before generating a fix — a similar failure may already be documented.{strategy_hint}

Original question: {question}
Database type: {db_type}
Failed query: {failed_query}
Error message: {error}

Schema:
{schema}

Fix the query. Return only the corrected query, no explanation."""

    def synthesize_response(self, question: str, merged_results: dict, query_trace: dict) -> str:
        return f"""Synthesize a clear, direct answer to the user's question from these database results.

Question: {question}

Results from databases:
{json.dumps(merged_results, indent=2)}

Rules:
- Answer the question directly in 1-3 sentences
- Include specific numbers/values from the results
- If results are empty, say so explicitly
- Do not mention internal query details in the answer"""

    def text_extraction(self, text: str, goal: str) -> str:
        return f"""Extract structured information from this text.

Goal: {goal}
Text: {text}

Return a JSON object with the extracted information. Example for sentiment:
{{"sentiment": "positive", "key_topics": ["service", "food"], "rating_implied": 4}}

Return only valid JSON."""

    def _dialect_rules(self, dialect: str) -> str:
        rules = {
            "postgresql": "use ILIKE for case-insensitive search, LIMIT for pagination",
            "sqlite": "use LIKE for search, no ILIKE, use strftime for dates",
            "duckdb": "use DuckDB analytical functions, SAMPLE for large datasets",
            "mongodb": "return a MongoDB aggregation pipeline as a JSON array",
        }
        return rules.get(dialect, "use standard SQL")
