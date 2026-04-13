# Oracle Forge — Team Falcon

**The Oracle Forge of Data Agent** | TRP1 FDE Programme | Week 8–9 | April 2026

A production-grade natural language data analytics agent that answers complex business questions across heterogeneous databases (PostgreSQL, MongoDB, SQLite, DuckDB) in a single response. Built against the UC Berkeley DataAgentBench benchmark.

---

## Team

| Name | Role |
|------|------|
| Natnael Alemseged | Driver |
| Yakob Dereje | Driver |
| Mamaru Yirga | Intelligence Officer |
| Ramlla Akmel | Intelligence Officer |
| Melaku Yilma | Signal Corps |
| Rahel Samson | Signal Corps |

---

## Repo Structure

```
oracle-forge/
├── kb/                          # LLM Knowledge Base (Intelligence Officers)
│   ├── AGENT.md                 # Master context file — loaded into agent at session start
│   ├── architecture/            # KB v1: Claude Code memory system, OpenAI data agent patterns,
│   │   ├── claude_code_memory.md          self-correction loop, tool scoping, DuckDB failure modes
│   │   ├── openai_data_agent_context.md
│   │   ├── self_correction_loop.md
│   │   ├── ddb_failure_modes.md
│   │   ├── dab_failure_modes.md
│   │   ├── tool_scoping_and_parallelism.md
│   │   ├── autodream_consolidation.md
│   │   ├── agent_probing_strategy.md
│   │   └── CHANGELOG.md
│   ├── domain/                  # KB v2: DAB dataset schemas, join key formats,
│   │   ├── yelp_schema.md                 unstructured fields, domain terminology
│   │   ├── schema_overview.md
│   │   ├── join_keys_glossary.md
│   │   ├── unstructured_fields_inventory.md
│   │   ├── domain_knowledge.md
│   │   ├── domain_terms.md
│   │   └── CHANGELOG.md
│   ├── evaluation/              # KB v3 (evaluation): DAB scoring method, harness schema,
│   │   ├── scoring_method.md              failure category reference
│   │   ├── dab_read.md
│   │   ├── ddb_read.md
│   │   └── CHANGELOG.md
│   └── corrections/             # KB v3 (corrections): running log of agent failures →
│       ├── corrections_log.md             root cause → fix (32 entries, 4 systemic patterns)
│       └── CHANGELOG.md
│
├── utils/                       # Shared utility modules (Intelligence Officers)
│   ├── join_key_resolver.py     # Resolves format mismatches across DBs (e.g. int vs "CUST-001")
│   ├── schema_introspector.py   # Unified schema introspection across all 4 DB types
│   ├── multi_pass_retrieval.py  # Vocab-expanded KB retrieval to catch edge-case corrections
│   ├── benchmark_harness_wrapper.py  # Evaluation harness with trace logging
│   └── README.md
│
├── probes/                      # Adversarial probe library (Intelligence Officers)
│   └── probes.md                # 15 probes across all 4 DAB failure categories with fixes
│
├── mcp/                         # MCP Toolbox config (Drivers)
│   └── tools.yaml               # DB connections: PostgreSQL, MongoDB, SQLite, DuckDB
│
├── planning/                    # AI-DLC sprint documents (Drivers)
│   ├── inception_v1.md          # Sprint 1 Inception — team-approved April 9, 2026
│   └── sprint_plan_driver2.md
│
├── signal/                      # Signal Corps engagement log
│   └── engagement_log.md        # Post links, community participation, resource acquisitions
│
├── requirements.txt
└── README.md
```

---

## Knowledge Base

The KB is the agent's persistent context, built using the Karpathy method: minimal, precise documents injected directly into the LLM context window. Every document is verified by an injection test before committing.

**Three layers:**

| Layer | Location | Contents |
|---|---|---|
| Architecture (v1) | `kb/architecture/` | Claude Code memory system, OpenAI 6-layer context design, self-correction loop, tool scoping, DuckDB/DAB failure modes |
| Domain (v2) | `kb/domain/` | Yelp dataset schema, join key format glossary, unstructured field inventory, domain term definitions |
| Corrections (v3) | `kb/corrections/` | 32 observed agent failures → root cause → correct approach. Read by agent at session start. |

The master context file is [kb/AGENT.md](kb/AGENT.md) — 12 critical rules covering schema boundaries, date parsing, query formatting, and cross-DB routing.

---

## Utilities

| Module | What it does |
|---|---|
| `join_key_resolver.py` | Detects and resolves ID format mismatches across databases before joins |
| `schema_introspector.py` | Single interface to introspect schema across PostgreSQL, MongoDB, SQLite, DuckDB |
| `multi_pass_retrieval.py` | Runs multiple vocabulary passes against KB to catch corrections phrased differently |
| `benchmark_harness_wrapper.py` | Wraps DAB evaluation with per-query trace logging and score output |

---

## Adversarial Probes

[probes/probes.md](probes/probes.md) contains 15 probes covering all 4 DAB failure categories:

- Multi-database routing failures
- Ill-formatted join key mismatches
- Unstructured text extraction failures
- Domain knowledge gaps

Each probe documents: query, expected failure, observed failure, fix applied, post-fix score.

---

## Benchmark

- Dataset: [UC Berkeley DataAgentBench](https://github.com/ucbepic/DataAgentBench) — 54 queries across 12 datasets, 4 DB types
- Current SOTA: PromptQL + Gemini 3.1 Pro at 54.3% pass@1
- Evaluation harness: `utils/benchmark_harness_wrapper.py`
- Score log: `eval/score_log.json` (populated after first benchmark run)

---

## Setup

```bash
# 1. Clone
git clone https://github.com/Natnael-Alemseged/oracle-forge.git
cd oracle-forge

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure MCP Toolbox
./toolbox --config mcp/tools.yaml
# Toolbox runs on http://localhost:5000

# 4. Verify connections
curl http://localhost:5000/v1/tools | python3 -m json.tool | grep name
```

Full setup instructions including database loading are in [kb/AGENT.md](kb/AGENT.md).
