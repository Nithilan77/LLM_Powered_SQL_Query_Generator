"""
semantic_baseline.py  --  Phase 2: same flow as naive, but the prompt now
contains BUSINESS MEANING (the semantic layer) instead of just column names.

Difference from naive_baseline.py:
  naive  -> prompt = "TABLE fact_orders: order_id (TEXT), order_total_usd (FLOAT)..."
  here   -> prompt = "...order_total_usd: THE REVENUE COLUMN. user_id: per-order,
                       NOT a person id; use unique_id for repeat buyers..."

Still 'dump everything' (all tables go in). Phase 3 adds RAG to send only the
relevant tables. We're isolating ONE change at a time so we can attribute the
improvement to the semantic layer specifically.

Run:  python semantic_baseline.py
"""

import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(__file__))
from llm import generate_sql            # noqa: E402
from semantic_layer import render_all   # noqa: E402

DB_PATH = os.environ.get("OLIST_DB", os.path.join("..", "data", "olist.db"))


def build_prompt(question: str) -> str:
    return f"""You are writing SQLite SQL for an e-commerce data warehouse.
Use the semantic descriptions below -- they tell you how each column should be
used, which the raw schema cannot. Follow the guidance carefully (grain,
revenue column, person vs order ids, etc.).

{render_all()}

Question: "{question}"

Write a single SQLite SQL query that answers it. Return only the SQL."""


def run_query(engine, sql: str):
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()
        cols = result.keys()
    return cols, rows


def answer(question: str, engine):
    print(f"\nQuestion: {question}")
    print("Generating SQL...")
    sql = generate_sql(build_prompt(question))
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
    questions = [
        "How many customers are repeat buyers versus one-time buyers?",
        "Which 5 states have the most canceled orders?",
        "What are the top 5 product categories by total revenue?",
    ]
    for q in questions:
        answer(q, engine)
        print("=" * 60)


if __name__ == "__main__":
    main()