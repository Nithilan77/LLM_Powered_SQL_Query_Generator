"""
rescore.py  --  Re-grade the saved checkpoint with BOTH comparators.

Spends ZERO API quota: it re-runs the gold SQL and re-compares against the
predicted SQL already stored in eval_checkpoint.jsonl. Use after changing the
comparator, or to see strict-vs-tolerant numbers on a finished run.

Run:  python rescore.py
"""

import json
import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(__file__))
from gold_olist import GOLD                       # noqa: E402
from comparator import results_match, subset_match  # noqa: E402

DB_PATH = os.environ.get("OLIST_DB", os.path.join("..", "data", "olist.db"))
CHECKPOINT = os.path.join(os.path.dirname(__file__), "eval_checkpoint.jsonl")

gold_by_id = {g["id"]: g for g in GOLD}


def run_sql(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


def main():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    rows = [json.loads(l) for l in open(CHECKPOINT) if l.strip()]

    strict_n = tolerant_n = 0
    by_diff = {}
    recovered = []

    for r in rows:
        g = gold_by_id[r["id"]]
        gold_rows = run_sql(engine, g["gold_sql"])

        # re-execute the stored prediction SQL (no LLM call)
        try:
            pred_rows = run_sql(engine, r["pred_sql"]) if r["pred_sql"] else []
            ok_strict = results_match(pred_rows, gold_rows, order_matters=g["order_matters"])
            ok_tol = subset_match(pred_rows, gold_rows, order_matters=g["order_matters"])
        except Exception:
            ok_strict = ok_tol = False

        strict_n += ok_strict
        tolerant_n += ok_tol
        d = r["difficulty"]
        by_diff.setdefault(d, [0, 0, 0])
        by_diff[d][0] += 1
        by_diff[d][1] += ok_strict
        by_diff[d][2] += ok_tol
        if ok_tol and not ok_strict:
            recovered.append(r["id"])

    n = len(rows)
    print(f"Re-scored {n} questions (no quota spent)\n")
    print(f"STRICT execution accuracy:         {strict_n}/{n} = {100*strict_n/n:.1f}%")
    print(f"SHAPE-TOLERANT execution accuracy: {tolerant_n}/{n} = {100*tolerant_n/n:.1f}%")
    print("\nBy difficulty (strict / tolerant):")
    for d in ["easy", "medium", "hard"]:
        if d in by_diff:
            tot, s, t = by_diff[d]
            print(f"  {d:7s}: {s}/{tot} strict  |  {t}/{tot} tolerant")
    if recovered:
        print(f"\nRecovered by shape-tolerant matching (were shape-only mismatches):")
        for rid in recovered:
            print(f"  {rid}")


if __name__ == "__main__":
    main()