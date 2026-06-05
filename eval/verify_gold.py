"""
verify_gold.py  --  Run every gold query and show its result.

Before a gold set can be trusted, each gold query must actually be correct.
This script runs them all against the real olist.db and prints the output so
you can eyeball each one. A gold query that errors or returns nonsense must be
fixed BEFORE running any eval -- otherwise you're measuring predictions against
wrong answers.

Run:  python verify_gold.py
"""

import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(__file__))
from gold_olist import GOLD  # noqa: E402

DB_PATH = os.environ.get("OLIST_DB", os.path.join("..", "data", "olist.db"))


def main():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    problems = 0
    for item in GOLD:
        print("=" * 70)
        print(f"[{item['id']}] ({item['difficulty']}) {item['question']}")
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(item["gold_sql"])).fetchall()
            print(f"  -> {len(rows)} rows")
            for r in rows[:8]:
                print("     ", tuple(r))
            if len(rows) > 8:
                print(f"      ... and {len(rows) - 8} more")
            if len(rows) == 0:
                print("  WARNING: gold query returned 0 rows -- is that expected?")
        except Exception as e:
            problems += 1
            print(f"  ERROR: {str(e).splitlines()[0]}")
    print("=" * 70)
    if problems:
        print(f"\n{problems} gold quer(ies) FAILED -- fix before evaluating.")
    else:
        print(f"\nAll {len(GOLD)} gold queries ran. Eyeball the results above for correctness.")


if __name__ == "__main__":
    main()