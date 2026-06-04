"""
rag_baseline.py  --  Phase 3: RAG schema linking in action.

Same flow as Phase 2, but the prompt now contains ONLY the tables the
retriever judged relevant to the question -- not all six.

On a 6-table DB this won't dramatically change accuracy (everything fit
before). What it PROVES is scalability: only relevant tables are sent, so
this same code works on a 200-table warehouse where dumping everything is
impossible. That's the interview point.

The script prints which tables were retrieved for each question so you can
SEE the retrieval doing its job.

Run:  python rag_baseline.py
"""

import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(__file__))
from llm import generate_sql        # noqa: E402
from retriever import SchemaRetriever  # noqa: E402

DB_PATH = os.environ.get("OLIST_DB", os.path.join("..", "data", "olist.db"))


def build_prompt(retrieved_schema: str, question: str) -> str:
    return f"""You are writing SQLite SQL for an e-commerce data warehouse.
Below are the database tables relevant to this question, with semantic
descriptions telling you how each column should be used. Follow the guidance
(grain, revenue column, person vs order ids, etc.).

{retrieved_schema}

Question: "{question}"

Write a single SQLite SQL query that answers it. Return only the SQL."""


def run_query(engine, sql: str):
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()
        cols = result.keys()
    return cols, rows


def answer(question: str, engine, retriever, k=3):
    retrieved = retriever.retrieve(question, k=k)
    print(f"\nQuestion: {question}")
    print(f"Retrieved tables (top {k}): {retrieved}")

    schema_text = retriever.render_retrieved(question, k=k)
    sql = generate_sql(build_prompt(schema_text, question))
    print(f"\nGenerated SQL:\n{sql}\n")

    try:
        cols, rows = run_query(engine, sql)
    except Exception as e:
        print(f"SQL FAILED to run: {e}")
        return
    print(f"Results ({len(rows)} rows):")
    print(" | ".join(str(c) for c in cols))
    print("-" * 50)
    for r in rows[:20]:
        print(" | ".join(str(v) for v in r))
    if len(rows) > 20:
        print(f"... and {len(rows) - 20} more rows")


def main():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    print("Loading retriever (first run downloads the embedding model)...")
    retriever = SchemaRetriever()

    questions = [
        "What are the top 5 product categories by total revenue?",
        "How many customers are repeat buyers versus one-time buyers?",
        "Which 5 sellers have the highest average review scores, with at least 50 reviews?",
    ]
    for q in questions:
        answer(q, engine, retriever, k=3)
        print("=" * 60)


if __name__ == "__main__":
    main()