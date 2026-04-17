"""
eval/run_query.py
-----------------
Single-query test runner. Instantiates the full agent stack and runs one question.

Usage:
    python eval/run_query.py --question "How many businesses are open in the Yelp dataset?"
    python eval/run_query.py --dataset yelp --question "Which users left the most reviews?"
"""
import argparse
import json
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from agent.models import QueryRequest
from agent.prompt_library import PromptLibrary
from agent.context_manager import ContextManager
from agent.response_synthesizer import ResponseSynthesizer
from agent.self_corrector import SelfCorrector
from agent.database_router import DatabaseRouter
from agent.query_executor import QueryExecutor
from agent.state_manager import StateManager
from agent.agent_core import AgentCore
from agent import llm_client

# Paths relative to project root
AGENT_MD   = "agent/AGENT.md"
CORRECTIONS = "kb/corrections/corrections_log.md"
DOMAIN_KB  = "kb/domain/domain_terms.md"

# Available databases per dataset
DATASET_DBS = {
    "yelp":         ["mongodb", "duckdb"],
    "bookreview":   ["postgresql", "sqlite"],
    "googlelocal":  ["postgresql", "sqlite"],
    "agnews":       ["mongodb", "sqlite"],
    "crmarenapro":  ["core_crm", "sales_pipeline", "support", "products_orders", "activities", "territory"],
    "DEPS_DEV_V1":  ["package_database", "project_database"],
}


def build_agent() -> AgentCore:
    prompts  = PromptLibrary()
    ctx      = ContextManager(AGENT_MD, CORRECTIONS, DOMAIN_KB)
    return AgentCore(ctx, prompts)


async def main():
    parser = argparse.ArgumentParser(description="Run a single query through Oracle Forge")
    parser.add_argument("--question", required=True, help="Natural language question")
    parser.add_argument("--dataset", default="yelp", choices=list(DATASET_DBS.keys()))
    parser.add_argument("--session-id", default="test-session")
    args = parser.parse_args()

    available_dbs = DATASET_DBS[args.dataset]
    request = QueryRequest(
        question=args.question,
        available_databases=available_dbs,
        session_id=args.session_id,
        dataset=args.dataset,
    )

    print(f"\nQuestion : {args.question}")
    print(f"Dataset  : {args.dataset}")
    print(f"DBs      : {available_dbs}\n")

    agent = build_agent()
    response = await agent.run(request)

    print("=" * 60)
    print(f"Answer   : {response.answer}")
    print(f"Confidence: {response.confidence}")
    if response.error:
        print(f"Error    : {response.error}")
    print("\nQuery trace:")
    for sq in response.query_trace.sub_queries:
        print(f"  [{sq.database_type}] {sq.query[:120]}")
    if response.query_trace.self_corrections:
        print(f"\nSelf-corrections: {len(response.query_trace.self_corrections)}")
        for c in response.query_trace.self_corrections:
            print(f"  attempt {c['attempt']}: {c['failure_type']}")
    print("=" * 60)

    # Log output path
    import glob
    logs = sorted(glob.glob("eval/run_logs/*.json"))
    if logs:
        print(f"\nFull trace logged to: {logs[-1]}")


if __name__ == "__main__":
    asyncio.run(main())
