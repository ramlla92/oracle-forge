# Oracle Forge — Team Falcon

**The Oracle Forge of Data Agent** | TRP1 FDE Programme | Week 8–9 | April 2026

## Team
| Name | Role |
|------|------|
| Natnael Alemseged | Driver 2 — Agent Logic & Context Engineering |
| Yakob Dereje | Driver 1 — Infrastructure & DB Connections |
| Mamaru Yirga | Intelligence Officer |
| Ramlla Akmel | Intelligence Officer |
| Melaku Yilma | Signal Corps |
| Rahel Samson | Signal Corps |

## What This Is
A production-grade natural language data analytics agent that answers complex business questions across PostgreSQL, MongoDB, SQLite, and DuckDB in a single response. Built on the UC Berkeley DataAgentBench (DAB) benchmark.

## Architecture
```
User question
    ↓
AgentCore.run()
    ↓
ContextManager.get_full_context()   ← Layer 1 (AGENT.md schema)
                                     ← Layer 2 (domain KB)
                                     ← Layer 3 (corrections log)
    ↓
analyze_intent() → LLM → {target_databases, requires_join}
    ↓
decompose_query() → [SubQuery(db_type, query, intent), ...]
    ↓
For each SubQuery:
    QueryExecutor → MCP Toolbox → DB result
    On failure: SelfCorrector.correct() → diagnose → retry (max 3)
    ↓
ResponseSynthesizer → human-readable answer + query_trace
    ↓
AgentCore._log_run() → eval/run_logs/<timestamp>.json
```

## Repo Structure
```
agent/          # Agent logic (Driver 2)
kb/             # LLM Knowledge Base — architecture, domain, corrections (Intelligence Officers)
mcp/            # MCP Toolbox config (tools.yaml)
eval/           # Benchmark harness and score log
probes/         # Adversarial probe library
utils/          # Schema introspector, join key resolver, multi-pass retrieval
planning/       # Sprint plans and inception documents
signal/         # Engagement log (Signal Corps)
db/             # Local SQLite and DuckDB files (gitignored)
```

## Setup
```bash
# 1. Clone repo
git clone <repo-url> && cd oracle-forge

# 2. Create .env (never commit)
# OPEN_ROUTER_KEY=...
# POSTGRES_USER=oracle_forge
# POSTGRES_PASSWORD=...
# POSTGRES_HOST=127.0.0.1
# POSTGRES_DB=yelp
# MONGO_HOST=127.0.0.1

# 3. Install dependencies
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 4. Set up local PostgreSQL
sudo -u postgres psql -c "CREATE USER oracle_forge WITH PASSWORD '...'; CREATE DATABASE yelp OWNER oracle_forge;"

# 5. Load DAB datasets
git clone https://github.com/ucbepic/DataAgentBench.git
cd DataAgentBench && bash setup/load_postgres.sh

# 6. Start MCP Toolbox
./toolbox --config mcp/tools.yaml

# 7. Verify
curl http://localhost:5000/v1/tools | python3 -m json.tool | grep name
```

## Linting
```bash
# Run linter
.venv/bin/python -m ruff check .

# Auto-fix safe issues
.venv/bin/python -m ruff check . --fix
```

## Benchmark
- Dataset: UC Berkeley DataAgentBench — github.com/ucbepic/DataAgentBench
- Score log: `eval/score_log.md`
