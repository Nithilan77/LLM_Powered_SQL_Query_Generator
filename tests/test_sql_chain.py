"""
Tests for the SqlChain self-correction loop.

These use a real in-memory SQLite DB plus a FAKE llm and FAKE embedder, so
they run in milliseconds with no API calls and no model download. That's the
payoff of making llm/retriever/engine injectable.

Run:  pytest tests/test_sql_chain.py -v
"""

import os
import sys

import numpy as np
import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
from sql_chain import SqlChain, _ensure_limit  # noqa: E402
from retriever import SchemaRetriever            # noqa: E402


@pytest.fixture
def engine():
    """In-memory SQLite with a tiny products table + a query_log."""
    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE dim_products (product_id TEXT, category_name TEXT)"))
        conn.execute(text("INSERT INTO dim_products VALUES ('p1','health_beauty'),('p2','toys')"))
        conn.execute(
            text(
                "CREATE TABLE query_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "question TEXT, generated_sql TEXT, tables_used TEXT, "
                "latency_ms INTEGER, success INTEGER)"
            )
        )
    return eng


@pytest.fixture
def retriever():
    """SchemaRetriever with a fake embedder (no model download)."""
    vocab = ["revenue", "category", "product", "customer", "seller", "review", "order"]

    def fake_embed(texts):
        return np.asarray(
            [[float(w in t.lower()) for w in vocab] for t in texts], dtype=np.float32
        )

    return SchemaRetriever(embedder=fake_embed)


def test_success_first_try(engine, retriever):
    chain = SqlChain(
        engine=engine,
        retriever=retriever,
        llm=lambda p: "SELECT category_name FROM dim_products",
    )
    r = chain.run("list categories")
    assert r.success
    assert r.attempts == 1
    assert not r.repaired


def test_self_corrects_after_one_failure(engine, retriever):
    def flaky(prompt):
        # The repair prompt contains this phrase; use it to branch.
        if "failed to execute" in prompt:
            return "SELECT category_name FROM dim_products"
        return "SELECT bad_col FROM dim_products"

    chain = SqlChain(engine=engine, retriever=retriever, llm=flaky)
    r = chain.run("list categories")
    assert r.success
    assert r.repaired
    assert r.attempts == 2


def test_gives_up_after_max_repairs(engine, retriever):
    chain = SqlChain(
        engine=engine,
        retriever=retriever,
        llm=lambda p: "SELECT never_exists FROM dim_products",
        max_repairs=2,
    )
    r = chain.run("list categories")
    assert not r.success
    assert r.attempts == 3  # 1 initial + 2 repairs
    assert r.error is not None


def test_does_not_retry_on_empty_results(engine, retriever):
    # A valid query returning 0 rows must NOT trigger a repair.
    calls = {"n": 0}

    def counting_llm(prompt):
        calls["n"] += 1
        return "SELECT category_name FROM dim_products WHERE category_name = 'nonexistent'"

    chain = SqlChain(engine=engine, retriever=retriever, llm=counting_llm)
    r = chain.run("find a missing category")
    assert r.success          # empty result is still a success
    assert len(r.rows) == 0
    assert calls["n"] == 1     # only called once -- no retry on empty


def test_ensure_limit():
    assert "LIMIT 1000" in _ensure_limit("SELECT * FROM t")
    assert _ensure_limit("SELECT * FROM t LIMIT 5").count("LIMIT") == 1
    # non-SELECT statements are left untouched
    assert _ensure_limit("PRAGMA table_info(t)") == "PRAGMA table_info(t)"