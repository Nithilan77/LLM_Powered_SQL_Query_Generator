"""
main.py  --  FastAPI backend for the Text-to-SQL system.

Endpoints:
  POST /query    {question} -> {sql, columns, rows, tables_used, attempts,
                                repaired, latency_ms, success, error}
  GET  /schema   -> the semantic layer (table/column descriptions) for the UI
  GET  /health   -> liveness check

The heavy objects (embedding model + retriever) load ONCE at startup, not per
request, so queries are fast. CORS is open for local dev (lock down for prod).

Run:  uvicorn api.main:app --reload --port 8000
"""

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
from sql_chain import SqlChain          # noqa: E402
from semantic_layer import SEMANTIC_LAYER  # noqa: E402
from guard import is_safe                # noqa: E402

app = FastAPI(title="Text-to-SQL API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only; restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the system ONCE at startup (embedding model + retriever are expensive).
_chain: SqlChain | None = None


def get_chain() -> SqlChain:
    global _chain
    if _chain is None:
        _chain = SqlChain()
    return _chain


@app.on_event("startup")
def _warmup():
    get_chain()  # pay the model-load cost at boot, not on first request


class QueryRequest(BaseModel):
    question: str


@app.post("/query")
def query(req: QueryRequest):
    question = req.question.strip()
    if not question:
        return {"success": False, "error": "Empty question."}

    res = get_chain().run(question)

    # Safety guard: never return a query that isn't a read-only SELECT.
    # (The chain only generates SELECTs, but we double-check before returning.)
    safe, reason = is_safe(res.sql)
    if not safe:
        return {
            "success": False,
            "sql": res.sql,
            "error": f"Blocked for safety: {reason}",
        }

    return {
        "success": res.success,
        "sql": res.sql,
        "columns": res.columns,
        "rows": [list(r) for r in res.rows],
        "tables_used": res.tables_used,
        "attempts": res.attempts,
        "repaired": res.repaired,
        "latency_ms": res.latency_ms,
        "error": res.error,
    }


@app.get("/schema")
def schema():
    """Return table + column descriptions so the UI can show a schema explorer."""
    out = []
    for table, entry in SEMANTIC_LAYER.items():
        out.append(
            {
                "table": table,
                "description": entry["description"],
                "columns": list(entry["columns"].keys()),
            }
        )
    return {"tables": out}


@app.get("/health")
def health():
    return {"status": "ok"}