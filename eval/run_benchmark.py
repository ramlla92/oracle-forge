"""
eval/run_benchmark.py
---------------------
Runs all queries for a DAB dataset through Oracle Forge and scores them
using each query's validate.py.

Usage:
    python eval/run_benchmark.py --dataset yelp
    python eval/run_benchmark.py --dataset yelp --trials 3
"""
import argparse
import asyncio
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.agent_core import AgentCore
from agent.context_manager import ContextManager
from agent.models import QueryRequest
from agent.prompt_library import PromptLibrary


def _resolve_dab_root() -> Path:
    """
    Resolve a readable DataAgentBench root path.

    Priority:
    1) DAB_ROOT from environment
    2) ~/DataAgentBench
    3) ../DataAgentBench relative to project root
    """
    env_root = os.getenv("DAB_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root).expanduser())

    project_root = Path(__file__).resolve().parents[1]
    candidates.extend([
        Path.home() / "DataAgentBench",
        project_root.parent / "DataAgentBench",
    ])

    for candidate in candidates:
        try:
            if candidate.exists() and os.access(candidate, os.R_OK | os.X_OK):
                return candidate
        except PermissionError:
            continue

    checked = ", ".join(str(p) for p in candidates)
    raise RuntimeError(
        "Could not locate a readable DataAgentBench directory. "
        f"Checked: {checked}. "
        "Set DAB_ROOT to a readable path, e.g. "
        f"DAB_ROOT={Path.home() / 'DataAgentBench'}."
    )


DAB_ROOT = _resolve_dab_root()

AGENT_MD    = "agent/AGENT.md"
CORRECTIONS = "kb/corrections/corrections_log.md"
DOMAIN_KB   = "kb/domain/domain_terms.md"

DATASET_DBS = {
    "yelp":         ["mongodb", "duckdb"],
    "bookreview":   ["postgresql_bookreview", "sqlite"],
    "googlelocal":  ["postgresql", "sqlite"],
    "agnews":       ["mongodb", "sqlite"],
    "crmarenapro":  ["core_crm", "sales_pipeline", "support", "products_orders", "activities", "territory"],
    "DEPS_DEV_V1":  ["package_database", "project_database"],
}


def load_validate(query_dir: Path):
    spec = importlib.util.spec_from_file_location("validate", query_dir / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.validate


def load_queries(dataset: str) -> list[dict]:
    dataset_dir = DAB_ROOT / f"query_{dataset}"
    if not dataset_dir.exists():
        raise RuntimeError(
            f"Dataset directory not found: {dataset_dir}. "
            "Verify DAB_ROOT points to your DataAgentBench clone."
        )
    if not os.access(dataset_dir, os.R_OK | os.X_OK):
        raise PermissionError(
            f"Dataset directory is not readable: {dataset_dir}. "
            "Fix permissions or point DAB_ROOT to a readable clone."
        )

    queries = []
    try:
        query_dirs = sorted(dataset_dir.glob("query[0-9]*"))
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot enumerate queries under {dataset_dir}. "
            "Grant read+execute permissions on this directory tree, or set "
            "DAB_ROOT to a location readable by the current user."
        ) from exc

    for query_dir in query_dirs:
        query_file = query_dir / "query.json"
        if not query_file.exists():
            continue
        question = json.loads(query_file.read_text())
        gt_file = query_dir / "ground_truth.csv"
        ground_truth = gt_file.read_text().strip() if gt_file.exists() else ""
        validate_fn = load_validate(query_dir) if (query_dir / "validate.py").exists() else None
        queries.append({
            "id": query_dir.name,
            "question": question,
            "ground_truth": ground_truth,
            "validate": validate_fn,
        })
    return queries


def build_agent() -> AgentCore:
    prompts = PromptLibrary()
    ctx = ContextManager(AGENT_MD, CORRECTIONS, DOMAIN_KB)
    return AgentCore(ctx, prompts)


async def run_one(agent: AgentCore, question: str, available_dbs: list[str],
                  session_id: str, dataset: str = "yelp") -> str:
    request = QueryRequest(
        question=question,
        available_databases=available_dbs,
        session_id=session_id,
        dataset=dataset,
    )
    response = await agent.run(request)
    return response.answer


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="yelp", choices=list(DATASET_DBS.keys()))
    parser.add_argument("--trials", type=int, default=1,
                        help="Number of trials per query (for pass@k scoring)")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()

    available_dbs = DATASET_DBS[args.dataset]
    queries = load_queries(args.dataset)
    if not queries:
        print(f"No queries found for dataset '{args.dataset}'")
        sys.exit(1)

    print(f"\nOracle Forge Benchmark — {args.dataset.upper()}")
    print(f"Queries : {len(queries)}   Trials : {args.trials}   DBs : {available_dbs}")
    print("=" * 60)

    results = []
    passed = 0
    total = 0

    for q in queries:
        qid = q["id"]
        question = q["question"]
        validate = q["validate"]
        trial_results = []

        print(f"\n[{qid}] {question}")

        for trial in range(args.trials):
            agent = build_agent()  # fresh agent per trial to reset session history
            session_id = f"{args.dataset}-{qid}-t{trial}"
            try:
                answer = await run_one(agent, question, available_dbs, session_id, dataset=args.dataset)
                print(f"  Trial {trial+1} answer: {answer[:120]}")
            except Exception as e:
                answer = f"ERROR: {e}"
                print(f"  Trial {trial+1} ERROR: {e}")

            if validate:
                ok, reason = validate(answer)
            else:
                ok, reason = False, "no validate.py"

            trial_results.append(
                {"trial": trial + 1, "answer": answer, "passed": ok, "reason": reason}
            )
            total += 1
            if ok:
                passed += 1

        any_pass = any(r["passed"] for r in trial_results)
        status = "PASS" if any_pass else "FAIL"
        print(f"  -> {status}  GT: {q['ground_truth'][:80]}")
        if not any_pass and trial_results:
            print(f"     Reason: {trial_results[-1]['reason']}")

        results.append({
            "query_id": qid,
            "question": question,
            "ground_truth": q["ground_truth"],
            "trials": trial_results,
            "any_pass": any_pass,
        })

    # Summary
    pass_rate = passed / total if total else 0
    any_pass_count = sum(1 for r in results if r["any_pass"])
    query_pass_rate = any_pass_count / len(queries) if queries else 0
    print("\n" + "=" * 60)
    print(
        f"Query-level pass@{args.trials}: {any_pass_count}/{len(queries)} "
        f"({query_pass_rate:.1%})  — at least 1 trial passed"
    )
    print(
        f"Trial-level pass rate:  {passed}/{total} "
        f"({pass_rate:.1%})  — across all individual trials"
    )

    # Write results JSON
    run_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or f"eval/run_logs/benchmark_{args.dataset}_{run_ts}.json"
    os.makedirs("eval/run_logs", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "dataset": args.dataset,
            "timestamp": run_ts,
            "trials": args.trials,
            "pass_count": any_pass_count,
            "total_queries": len(queries),
            "pass_at_k": pass_rate,
            "results": results,
        }, f, indent=2)
    print(f"Full results → {out_path}")

    # Update score_log.md
    _update_score_log(args.dataset, any_pass_count, len(queries), args.trials, run_ts)


def _update_score_log(dataset: str, passed: int, total: int, trials: int, ts: str):
    # passed/total here is query-level (any_pass_count / total_queries)
    score_pct = f"{passed/total:.0%}" if total else "0%"
    row = f"| {ts} | {dataset} | {passed}/{total} | {score_pct} | query-pass@{trials} | — |\n"
    log_path = "eval/score_log.md"
    with open(log_path, "a") as f:
        f.write(row)
    print(f"Score logged → {log_path}")


if __name__ == "__main__":
    asyncio.run(main())
