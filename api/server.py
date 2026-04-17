"""
api/server.py
-------------
Public-facing HTTP API for Oracle Forge.
Accepts a natural-language question and returns the agent's answer.

Usage:
    source .venv/bin/activate && source .env
    uvicorn api.server:app --port 8080

Expose publicly via Cloudflare Tunnel (no account needed for ephemeral URL):
    cloudflared tunnel --url http://localhost:8080
"""
import uuid
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.agent_core import AgentCore
from agent.context_manager import ContextManager
from agent.models import QueryRequest
from agent.prompt_library import PromptLibrary

load_dotenv()

AGENT_MD    = "agent/AGENT.md"
CORRECTIONS = "kb/corrections/corrections_log.md"
DOMAIN_KB   = "kb/domain/domain_terms.md"

DATASET_DBS = {
    "yelp":       ["mongodb", "duckdb"],
    "bookreview": ["postgresql_bookreview", "sqlite"],
    "agnews":     ["mongodb", "sqlite"],
    "GITHUB_REPOS": ["metadata_database", "artifacts_database"],
}

app = FastAPI(title="Oracle Forge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryInput(BaseModel):
    question: str
    dataset: Optional[str] = "yelp"
    session_id: Optional[str] = None


class QueryOutput(BaseModel):
    answer: str
    session_id: str
    dataset: str
    confidence: float


def _build_agent() -> AgentCore:
    prompts = PromptLibrary()
    ctx = ContextManager(AGENT_MD, CORRECTIONS, DOMAIN_KB)
    return AgentCore(ctx, prompts)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/datasets")
def list_datasets():
    return {"datasets": list(DATASET_DBS.keys())}


@app.post("/query", response_model=QueryOutput)
async def query(body: QueryInput):
    if body.dataset not in DATASET_DBS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown dataset '{body.dataset}'. Valid options: {list(DATASET_DBS.keys())}",
        )

    session_id = body.session_id or str(uuid.uuid4())
    available_dbs = DATASET_DBS[body.dataset]

    agent = _build_agent()
    request = QueryRequest(
        question=body.question,
        available_databases=available_dbs,
        session_id=session_id,
    )

    try:
        response = await agent.run(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return QueryOutput(
        answer=response.answer,
        session_id=session_id,
        dataset=body.dataset,
        confidence=response.confidence,
    )
