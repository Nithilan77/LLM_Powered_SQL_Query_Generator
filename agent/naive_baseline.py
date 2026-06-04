"""
naive_baseline.py  --  Phase 1: the deliberately DUMB version.

What it does:
  1. Reads the schema of EVERY table in olist.db (the naive part).
  2. Pastes ALL of it into a prompt.
  3. Asks Gemini to write SQL for the user's question.
  4. Runs that SQL and prints the results.

Why build the dumb version first?
  - You'll SEE the magic happen end-to-end on day one.
  - It becomes your BASELINE accuracy number. Later, RAG will be compared
    against this ("RAG improved accuracy from X% to Y%") -- and that comparison
    is half your interview story.
  - On a 6-table DB it works fine. The whole point of Phase 3 (RAG) is that
    this approach BREAKS when a database has 200 tables. You need to feel that.

Run:  python naive_baseline.py
"""

import os
import sys

from sqlalchemy import create_engine, text, inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from llm import generate_sql  # noqa: E402

DB_PATH = os.environ.get("OLIST_DB", os.path.join("..", "data", "olist.db"))


def get_full_schema(engine) -> str:
    """
    Build a text description of EVERY table and its columns.
    This is the 'dump everything' approach we'll later replace with RAG.
    """
    inspector = inspect(engine)
    lines = []
    for table_name in inspector.get_table_names():
        if table_name == "query_log":
            continue  # internal observability table, not for querying
        cols = inspector.get_columns(table_name)
        col_str = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
        lines.append(f"TABLE {table_name}: {col_str}")
    return "\n".join(lines)


def build_prompt(schema: str, question: str) -> str:
    return f"""Given the following SQLite database schema:

{schema}

Write a single SQLite SQL query to answer this question:
"{question}"

Return only the SQL query."""


def run_query(engine, sql: str):
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()
        cols = result.keys()
    return cols, rows


def answer(question: str, engine):
    schema = get_full_schema(engine)
    prompt = build_prompt(schema, question)

    print(f"\nQuestion: {question}")
    print("Generating SQL...")
    sql = generate_sql(prompt)
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

    # A few sample questions to try. Edit / add your own.
    questions = [
        "What is the monthly revenue trend in 2018?",
        "Which 5 sellers have the highest average review scores, with at least 50 reviews?",
        "How many customers are repeat buyers versus one-time buyers?",
    ]
    for q in questions:
        answer(q, engine)
        print("=" * 60)


if __name__ == "__main__":
    main()