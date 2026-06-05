"""
comparator.py  --  Execution-accuracy comparison for the eval harness.

The standard text-to-SQL metric is EXECUTION ACCURACY: run the predicted SQL
and the gold SQL, and check whether they return the SAME result -- NOT whether
the query text matches. Two very different queries can be equally correct
(different aliases, join order, column order), so comparing text is wrong.

Subtleties this handles:
  - Order independence: unless the question implies ordering, {(A,1),(B,2)} ==
    {(B,2),(A,1)}. We compare as multisets of rows by default.
  - Float tolerance: SUM/AVG can differ in the last decimal between two correct
    queries. We round floats to a tolerance before comparing.
  - A predicted query that ERRORS is simply incorrect (never matches).

We deliberately do NOT try to be clever about "semantically equivalent but
different columns" -- if the gold returns (category, revenue) and the
prediction returns (category, revenue, count), they differ. Gold defines the
expected shape.
"""

from collections import Counter


def _normalize_value(v, float_tol: int = 2):
    """Round floats so two correct aggregations don't differ in the last digit."""
    if isinstance(v, float):
        return round(v, float_tol)
    return v


def _normalize_rows(rows, float_tol: int = 2):
    """Turn rows into a hashable, comparison-ready form."""
    return [tuple(_normalize_value(v, float_tol) for v in row) for row in rows]


def results_match(
    pred_rows,
    gold_rows,
    order_matters: bool = False,
    float_tol: int = 2,
) -> bool:
    """
    Return True if the predicted result set matches the gold result set.

    order_matters=False (default): compare as multisets (row order ignored).
    order_matters=True: compare as ordered lists (for 'top N', 'ranked' Qs
                        where the SEQUENCE is part of the answer).
    """
    pred = _normalize_rows(pred_rows, float_tol)
    gold = _normalize_rows(gold_rows, float_tol)

    if order_matters:
        return pred == gold
    # multiset comparison: same rows, same multiplicities, any order
    return Counter(pred) == Counter(gold)


def compare_sql(engine, pred_sql: str, gold_rows, order_matters=False, float_tol=2):
    """
    Execute pred_sql and compare to precomputed gold_rows.
    Returns (is_correct, error_or_None). A query that errors is incorrect.
    """
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            pred_rows = conn.execute(text(pred_sql)).fetchall()
    except Exception as e:
        return False, str(e).split("\n")[0]

    return results_match(pred_rows, gold_rows, order_matters, float_tol), None