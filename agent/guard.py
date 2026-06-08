"""
guard.py  --  Safety guard: only allow read-only SELECT queries.

A naive guard greps for words like DELETE/DROP. That's fragile: it false-positives
on legitimate text (a column literally named 'deleted_at') and misses tricks
(stacked statements, comments). We do better:

  1. Strip SQL comments.
  2. Reject multiple statements (no '; DROP TABLE ...' stacking).
  3. Require the single statement to START with SELECT or WITH (CTE).
  4. Block any write keyword as a whole word, as a backstop.

This is defense-in-depth: the generator is told to write only SELECTs, but we
never TRUST that -- we verify before executing/returning.
"""

import re

# Write/DDL keywords that must never appear in a read-only query.
_FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "replace", "merge", "grant", "revoke", "attach", "detach", "pragma",
    "vacuum", "reindex",
}


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)          # line comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)  # block comments
    return sql


def is_safe(sql: str) -> tuple[bool, str]:
    """
    Return (True, '') if the SQL is a single read-only SELECT/CTE,
    else (False, reason).
    """
    if not sql or not sql.strip():
        return False, "empty query"

    clean = _strip_comments(sql).strip().rstrip(";").strip()

    # No stacked statements (a remaining ';' means multiple statements).
    if ";" in clean:
        return False, "multiple statements are not allowed"

    lowered = clean.lower()

    # Must start with SELECT or WITH (CTE that resolves to a SELECT).
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return False, "only SELECT queries are allowed"

    # Backstop: no write keyword as a standalone word.
    for kw in _FORBIDDEN:
        if re.search(rf"\b{kw}\b", lowered):
            return False, f"forbidden keyword: {kw}"

    return True, ""


if __name__ == "__main__":
    tests = [
        "SELECT * FROM dim_users",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "DELETE FROM dim_users",
        "SELECT * FROM t; DROP TABLE t",
        "SELECT deleted_at FROM t",  # legitimate: 'deleted_at' is a column
        "DROP TABLE dim_users",
        "SELECT * FROM t -- ; DROP TABLE t",  # comment hiding a drop
    ]
    for t in tests:
        print(is_safe(t), "<-", t)