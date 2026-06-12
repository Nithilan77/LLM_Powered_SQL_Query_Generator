"""
sql_chain.py  --  Phase 5: the orchestrator + self-correction loop.

This is the heart of the system. It ties every phase together:

    question
       |
       v
   [retrieve]  RAG: pick relevant tables           (retriever.py)
       |
       v
   [prompt]    build prompt w/ semantic layer      (semantic_layer.py)
       |
       v
   [generate]  ask Gemini for SQL                   (llm.py)
       |
       v
   [execute]   run against SQLite
       |
       +---- error? ----> [repair] feed error back to LLM, retry (<= MAX_REPAIRS)
       |
       v
   {sql, rows, columns, attempts, repaired, error}

SELF-CORRECTION DESIGN (decided deliberately):
  - Retry ONLY on execution errors (the DB objectively says the query is
    broken). NOT on empty results -- 0 rows is often the correct answer, and
    retrying there optimizes for "returns rows" instead of "is correct",
    which can turn correct queries into wrong ones.
  - MAX_REPAIRS = 2. If the model can fix its error it almost always does on
    the first repair; a second catches stragglers; beyond that it loops or
    faces an unfixable error and just burns quota.

The LLM and DB are both injectable so we can unit-test the loop with fakes
(no API calls, no real DB) -- see the __main__ block.
"""

import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(__file__))
from llm import generate_sql as real_generate_sql  # noqa: E402
from retriever import SchemaRetriever                # noqa: E402

DB_PATH = os.environ.get(
    "OLIST_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "olist.db"),
)
MAX_REPAIRS = 2
RESULT_ROW_LIMIT = 1000  # safety cap injected if the query has no LIMIT


@dataclass
class QueryResult:
    """Everything that happened while answering one question."""
    question: str
    sql: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    tables_used: list = field(default_factory=list)
    attempts: int = 0          # total generation attempts (1 = no repair needed)
    repaired: bool = False     # did we have to fix at least once?
    success: bool = False
    error: Optional[str] = None
    latency_ms: int = 0


def _ensure_limit(sql: str, limit: int = RESULT_ROW_LIMIT) -> str:
    """
    Inject a LIMIT if the query is a SELECT without one, so a careless
    'select * from fact_orders' doesn't return 112k rows to the browser.
    Aggregations with their own LIMIT are left alone.
    """
    if re.search(r"\blimit\b", sql, re.IGNORECASE):
        return sql
    if sql.lstrip().lower().startswith("select"):
        return f"{sql}\nLIMIT {limit}"
    return sql


def _build_initial_prompt(schema_text: str, question: str) -> str:
    return f"""You are writing SQLite SQL for an e-commerce data warehouse.
Below are the relevant tables with semantic descriptions telling you how each
column should be used. Follow the guidance carefully (grain: count DISTINCT
order_id for orders; revenue = SUM(order_total_usd); person identity = unique_id,
not user_id).

Output rules:
- When the question asks for a ranking, "top N", "most", "highest", "lowest",
  or "which X by Y", SELECT BOTH the grouping label AND the metric you ORDER BY
  (e.g. SELECT state, COUNT(...) -- not just state).
- When the question asks "how many" as a single total, return ONE scalar value
  (wrap grouped logic in an outer COUNT/aggregate); do not return one row per group.

{schema_text}

Question: "{question}"

Write a single SQLite SQL query that answers it. Return only the SQL."""


def _build_repair_prompt(schema_text: str, question: str, bad_sql: str, error: str) -> str:
    """
    The repair prompt. We give the model: the schema, the original question,
    the SQL it wrote, and the EXACT database error. This targeted feedback is
    what makes the loop effective -- the model can see precisely what failed.
    """
    return f"""You wrote a SQLite query that failed to execute. Fix it.

Relevant tables:
{schema_text}

Question: "{question}"

The SQL you wrote:
{bad_sql}

The database returned this error:
{error}

Write a corrected single SQLite SQL query. Return only the SQL."""


class SqlChain:
    """
    Orchestrates the full question -> SQL -> results pipeline with
    self-correction. Dependencies are injectable for testing.
    """

    def __init__(
        self,
        engine=None,
        retriever: Optional[SchemaRetriever] = None,
        llm: Optional[Callable[[str], str]] = None,
        k: int = 4,
        max_repairs: int = MAX_REPAIRS,
    ):
        self.engine = engine or create_engine(f"sqlite:///{DB_PATH}")
        self.retriever = retriever if retriever is not None else SchemaRetriever()
        self.llm = llm or real_generate_sql
        self.k = k
        self.max_repairs = max_repairs

    def _execute(self, sql: str):
        """Run SQL. Returns (columns, rows). Raises on DB error."""
        sql = _ensure_limit(sql)
        with self.engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchall()
            cols = list(result.keys())
        return cols, rows

    def run(self, question: str) -> QueryResult:
        start = time.time()
        res = QueryResult(question=question)

        # --- retrieve relevant tables (RAG) ---
        res.tables_used = self.retriever.retrieve(question, k=self.k)
        schema_text = self.retriever.render_retrieved(question, k=self.k)

        # --- first generation attempt ---
        sql = self.llm(_build_initial_prompt(schema_text, question))
        res.attempts = 1

        # --- execute, with up to max_repairs self-correction passes ---
        for repair_num in range(self.max_repairs + 1):
            res.sql = sql
            try:
                cols, rows = self._execute(sql)
                res.columns, res.rows = cols, rows
                res.success = True
                res.error = None
                break  # success -> stop
            except Exception as e:
                res.error = str(e).split("\n")[0]  # first line of the error
                if repair_num == self.max_repairs:
                    # out of repairs -> give up, keep the last error
                    break
                # otherwise: REPAIR. Feed the error back and try again.
                res.repaired = True
                repair_prompt = _build_repair_prompt(
                    schema_text, question, sql, res.error
                )
                sql = self.llm(repair_prompt)
                res.attempts += 1

        res.latency_ms = int((time.time() - start) * 1000)
        self._log(res)
        return res

    def _log(self, res: QueryResult):
        """Write the attempt to query_log for observability (best-effort)."""
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO query_log "
                        "(question, generated_sql, tables_used, latency_ms, success) "
                        "VALUES (:q, :sql, :tu, :lat, :ok)"
                    ),
                    {
                        "q": res.question,
                        "sql": res.sql,
                        "tu": ",".join(res.tables_used),
                        "lat": res.latency_ms,
                        "ok": 1 if res.success else 0,
                    },
                )
        except Exception:
            pass  # logging must never break the actual query


def _pretty_print(res: QueryResult):
    print(f"\nQuestion: {res.question}")
    print(f"Tables used: {res.tables_used}")
    print(f"Attempts: {res.attempts}  Repaired: {res.repaired}  Success: {res.success}")
    print(f"Latency: {res.latency_ms}ms")
    print(f"\nSQL:\n{res.sql}\n")
    if res.success:
        print(f"Results ({len(res.rows)} rows):")
        print(" | ".join(str(c) for c in res.columns))
        print("-" * 50)
        for r in res.rows[:20]:
            print(" | ".join(str(v) for v in r))
        if len(res.rows) > 20:
            print(f"... and {len(res.rows) - 20} more rows")
    else:
        print(f"FAILED after {res.attempts} attempts. Last error: {res.error}")


def main():
    chain = SqlChain()
    questions = [
        "What are the top 5 product categories by total revenue?",
        "How many customers are repeat buyers versus one-time buyers?",
        "Which 5 sellers have the highest average review scores, with at least 50 reviews?",
        "What is the monthly revenue trend in 2018?",
    ]
    for q in questions:
        _pretty_print(chain.run(q))
        print("=" * 60)


if __name__ == "__main__":
    main()