"""
run_eval.py  --  The eval harness runner.

For each gold question:
  1. ask the system (SqlChain) for predicted SQL + its executed result
  2. run the GOLD sql to get the reference result
  3. compare results (execution accuracy) via comparator
  4. checkpoint the outcome to disk immediately

RESUMABLE: results are written to a JSON-lines checkpoint as we go. If the
free-tier daily quota cuts us off (or we Ctrl-C), re-running SKIPS questions
already done and continues. This is essential on a 1000/day quota.

Reports: overall execution accuracy, breakdown by difficulty, repair rate
(how often self-correction fired and saved a query), and average latency.

Usage:
  python run_eval.py                 # run all, resuming if checkpoint exists
  python run_eval.py --fresh         # ignore checkpoint, start over
  python run_eval.py --limit 5       # only first 5 (smoke test / quota saving)
"""

import argparse
import json
import os
import sys
import time

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from gold_olist import GOLD            # noqa: E402
from comparator import results_match   # noqa: E402

DB_PATH = os.environ.get("OLIST_DB", os.path.join("..", "data", "olist.db"))
CHECKPOINT = os.path.join(os.path.dirname(__file__), "eval_checkpoint.jsonl")


def load_done():
    """Return dict of {id: result} already checkpointed."""
    done = {}
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT) as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    done[r["id"]] = r
    return done


def append_checkpoint(record):
    with open(CHECKPOINT, "a") as f:
        f.write(json.dumps(record) + "\n")


def run_gold(engine, gold_sql):
    with engine.connect() as conn:
        return conn.execute(text(gold_sql)).fetchall()


def evaluate(chain, engine, limit=None, fresh=False, delay=7.0):
    if fresh and os.path.exists(CHECKPOINT):
        os.remove(CHECKPOINT)

    done = load_done()
    items = GOLD[:limit] if limit else GOLD

    first = True
    for item in items:
        if item["id"] in done:
            continue  # resume: skip already-evaluated questions

        # Pace requests to respect the free-tier per-minute limit (10/min).
        # Sleep BEFORE each call except the first.
        if not first:
            time.sleep(delay)
        first = False

        # 1. system prediction (this spends an API call, maybe two if it repairs)
        try:
            res = chain.run(item["question"])
        except Exception as e:
            # Quota exhausted or other fatal LLM error. Stop cleanly WITHOUT
            # crashing: the checkpoint keeps everything done so far, so a
            # re-run tomorrow (after quota resets) resumes from here.
            msg = str(e).splitlines()[0]
            print(f"\n!! Stopping early: {msg}")
            print(f"   Progress saved. {len(done)} done. Re-run to resume after quota resets.")
            break

        # 2. gold reference result
        gold_rows = run_gold(engine, item["gold_sql"])

        # 3. compare
        if res.success:
            correct = results_match(
                res.rows, gold_rows, order_matters=item["order_matters"]
            )
        else:
            correct = False  # a prediction that errored is incorrect

        record = {
            "id": item["id"],
            "difficulty": item["difficulty"],
            "question": item["question"],
            "correct": bool(correct),
            "pred_success": bool(res.success),
            "repaired": bool(res.repaired),
            "attempts": res.attempts,
            "latency_ms": res.latency_ms,
            "pred_sql": res.sql,
            "pred_error": res.error,
        }
        append_checkpoint(record)
        done[item["id"]] = record

        mark = "OK " if correct else "XX "
        rep = " (repaired)" if res.repaired else ""
        print(f"{mark}[{item['id']}] {item['difficulty']}{rep}")
        if not correct:
            why = res.error if not res.success else "result mismatch"
            print(f"      why: {why}")

    return [done[i["id"]] for i in items if i["id"] in done]


def report(results):
    n = len(results)
    if n == 0:
        print("No results.")
        return
    correct = sum(r["correct"] for r in results)
    repaired = sum(r["repaired"] for r in results)
    repaired_and_correct = sum(r["repaired"] and r["correct"] for r in results)
    avg_latency = sum(r["latency_ms"] for r in results) / n

    print("\n" + "=" * 60)
    print(f"EXECUTION ACCURACY: {correct}/{n} = {100*correct/n:.1f}%")
    print(f"Average latency: {avg_latency:.0f} ms")
    print(f"Self-correction fired on {repaired}/{n} queries; "
          f"{repaired_and_correct} of those ended correct")

    print("\nBy difficulty:")
    for diff in ["easy", "medium", "hard"]:
        sub = [r for r in results if r["difficulty"] == diff]
        if sub:
            c = sum(r["correct"] for r in sub)
            print(f"  {diff:7s}: {c}/{len(sub)} = {100*c/len(sub):.0f}%")

    failures = [r for r in results if not r["correct"]]
    if failures:
        print("\nFailures:")
        for r in failures:
            why = r["pred_error"] if not r["pred_success"] else "result mismatch"
            print(f"  [{r['id']}] {why}")
    print("=" * 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="ignore checkpoint, start over")
    ap.add_argument("--limit", type=int, default=None, help="only first N questions")
    ap.add_argument("--delay", type=float, default=7.0, help="seconds between questions (rate-limit pacing)")
    args = ap.parse_args()

    from sql_chain import SqlChain

    engine = create_engine(f"sqlite:///{DB_PATH}")
    print("Loading system (retriever + chain)...")
    chain = SqlChain(engine=engine)

    results = evaluate(chain, engine, limit=args.limit, fresh=args.fresh, delay=args.delay)
    report(results)


if __name__ == "__main__":
    main()