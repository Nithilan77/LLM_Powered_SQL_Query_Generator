"""
run_ablation.py  --  Measure the contribution of each component.

Runs the full 40-question eval several times, each with one part of the system
turned off, so we can attribute accuracy to each component:

  full              semantic layer + RAG + self-correction   (the real system)
  no_repair         disable the self-correction loop
  no_semantic       bare schema (column names only, no descriptions)
  no_rag            send ALL tables (no retrieval)
  bare              no semantic layer AND no RAG (closest to naive baseline)

Each config writes its own checkpoint (ablation_<config>.jsonl) and is
resumable. At the end it prints a comparison table.

Needs a provider with enough quota (Groq recommended). ~40 calls per config.

Run:  python run_ablation.py
      python run_ablation.py --configs full no_semantic   # subset
      python run_ablation.py --delay 0                     # Groq can go fast
"""

import argparse
import json
import os
import random
import sys
import time

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from gold_olist import GOLD                       # noqa: E402
from comparator import results_match, subset_match  # noqa: E402

DB_PATH = os.environ.get("OLIST_DB", os.path.join("..", "data", "olist.db"))

# config name -> SqlChain kwargs
CONFIGS = {
    "full":        dict(use_semantic_layer=True,  use_rag=True,  max_repairs=2),
    "no_repair":   dict(use_semantic_layer=True,  use_rag=True,  max_repairs=0),
    "no_semantic": dict(use_semantic_layer=False, use_rag=True,  max_repairs=2),
    "no_rag":      dict(use_semantic_layer=True,  use_rag=False, max_repairs=2),
    "bare":        dict(use_semantic_layer=False, use_rag=False, max_repairs=2),
}


def ckpt_path(config):
    return os.path.join(os.path.dirname(__file__), f"ablation_{config}.jsonl")


def load_done(config):
    done = {}
    p = ckpt_path(config)
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line:
                r = json.loads(line)
                done[r["id"]] = r
    return done


def run_gold(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


def run_config(config, engine, delay, items):
    from sql_chain import SqlChain
    from retriever import SchemaRetriever

    kwargs = CONFIGS[config]
    print(f"\n=== Running config: {config}  ({kwargs}) ===")
    retriever = SchemaRetriever()  # shared embedding load
    chain = SqlChain(engine=engine, retriever=retriever, **kwargs)

    done = load_done(config)
    first = True
    for item in items:
        if item["id"] in done:
            continue
        if not first:
            time.sleep(delay)
        first = False
        try:
            res = chain.run(item["question"])
        except Exception as e:
            print(f"  !! stopping {config} early: {str(e).splitlines()[0]}")
            break
        gold_rows = run_gold(engine, item["gold_sql"])
        strict = res.success and results_match(res.rows, gold_rows, order_matters=item["order_matters"])
        tol = res.success and subset_match(res.rows, gold_rows, order_matters=item["order_matters"])
        rec = {
            "id": item["id"], "difficulty": item["difficulty"],
            "correct": bool(strict), "correct_tolerant": bool(tol),
            "repaired": bool(res.repaired), "attempts": res.attempts,
            "success": bool(res.success),
        }
        with open(ckpt_path(config), "a") as f:
            f.write(json.dumps(rec) + "\n")
        done[item["id"]] = rec
        print(f"  {'OK' if strict else 'XX'} [{item['id']}] {item['difficulty']}"
              + (" (repaired)" if res.repaired else ""))
    return [done[i["id"]] for i in items if i["id"] in done]


def summarize(config, results):
    n = len(results)
    if n == 0:
        return None
    strict = sum(r["correct"] for r in results)
    tol = sum(r.get("correct_tolerant", r["correct"]) for r in results)
    repaired = sum(r["repaired"] for r in results)
    return {"config": config, "n": n, "strict": strict, "tolerant": tol, "repaired": repaired}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=["full", "no_semantic", "bare"],
                    help="which configs to run (default: the semantic-layer comparison)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between questions")
    ap.add_argument("--subset", type=int, default=None,
                    help="run a fixed random N-question subset (deterministic, seed=42)")
    ap.add_argument("--fresh", action="store_true", help="delete checkpoints and restart")
    args = ap.parse_args()

    engine = create_engine(f"sqlite:///{DB_PATH}")

    # Deterministic subset: same questions for every config.
    items = list(GOLD)
    if args.subset:
        rng = random.Random(42)
        items = rng.sample(items, min(args.subset, len(items)))
        items.sort(key=lambda x: x["id"])  # stable order
        print(f"Using fixed {len(items)}-question subset (seed=42).")

    summaries = []
    for config in args.configs:
        if args.fresh and os.path.exists(ckpt_path(config)):
            os.remove(ckpt_path(config))
        results = run_config(config, engine, args.delay, items)
        s = summarize(config, results)
        if s:
            summaries.append(s)

    # comparison table
    print("\n" + "=" * 64)
    print(f"{'config':<14}{'n':>4}{'strict':>10}{'tolerant':>11}{'repaired':>10}")
    print("-" * 64)
    for s in summaries:
        sp = f"{s['strict']}/{s['n']} ({100*s['strict']/s['n']:.0f}%)"
        tp = f"{s['tolerant']}/{s['n']} ({100*s['tolerant']/s['n']:.0f}%)"
        print(f"{s['config']:<14}{s['n']:>4}{sp:>12}{tp:>13}{s['repaired']:>8}")
    print("=" * 64)

    # quick deltas vs full
    full = next((s for s in summaries if s["config"] == "full"), None)
    if full:
        print("\nContribution vs 'full' (strict accuracy):")
        fa = 100 * full["strict"] / full["n"]
        for s in summaries:
            if s["config"] == "full":
                continue
            a = 100 * s["strict"] / s["n"]
            print(f"  removing -> {s['config']:<12}: {a:.0f}%  (full is {fa:.0f}%, delta {fa-a:+.0f} pts)")


if __name__ == "__main__":
    main()