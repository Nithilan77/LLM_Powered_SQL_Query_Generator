"""
seed.py  --  Load raw Olist CSVs into a star-schema SQLite database.

Run once:   python seed.py
Produces:   data/olist.db   with tables:
            fact_orders, dim_users, dim_products, dim_sellers,
            dim_reviews, dim_geography, query_log

The "grain" of fact_orders is ONE ROW PER ORDER LINE ITEM.
Each row carries the measures (revenue, freight) + foreign keys to the dims.
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text

# ---- config -------------------------------------------------------------
# Folder that holds the 9 raw olist_*.csv files. Edit if yours differs.
RAW_DIR = os.environ.get("OLIST_RAW_DIR", "olist")
DB_PATH = os.path.join("data", "olist.db")
# -------------------------------------------------------------------------


def _read(name: str) -> pd.DataFrame:
    """Read one raw CSV by its Olist filename (without extension)."""
    path = os.path.join(RAW_DIR, f"{name}.csv")
    return pd.read_csv(path)


def build_dim_geography(geo: pd.DataFrame) -> pd.DataFrame:
    """
    Raw geolocation has MANY rows per zip prefix (one per lat/lng ping).
    We collapse to one representative row per zip prefix: the mean lat/lng
    and the most common city/state. This makes it a clean dimension keyed
    by zip prefix.
    """
    agg = (
        geo.groupby("geolocation_zip_code_prefix")
        .agg(
            lat=("geolocation_lat", "mean"),
            lng=("geolocation_lng", "mean"),
            city=("geolocation_city", lambda s: s.mode().iat[0] if not s.mode().empty else None),
            state=("geolocation_state", lambda s: s.mode().iat[0] if not s.mode().empty else None),
        )
        .reset_index()
        .rename(columns={"geolocation_zip_code_prefix": "zip_code_prefix"})
    )
    agg.insert(0, "geo_id", range(1, len(agg) + 1))
    return agg


def build_dim_users(customers: pd.DataFrame) -> pd.DataFrame:
    """
    One row per customer_id (the per-order customer key Olist actually uses
    in the orders table). We keep customer_unique_id so cohort/repeat-buyer
    questions are still answerable.
    """
    return customers.rename(
        columns={
            "customer_id": "user_id",
            "customer_unique_id": "unique_id",
            "customer_zip_code_prefix": "zip_code_prefix",
            "customer_city": "city",
            "customer_state": "state",
        }
    )[["user_id", "unique_id", "zip_code_prefix", "city", "state"]]


def build_dim_products(products: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    """
    Join the Portuguese category name to its English translation so that
    questions like 'top categories' return readable names.
    """
    merged = products.merge(translation, on="product_category_name", how="left")
    # Prefer the English name; fall back to the original if no translation.
    merged["category_name"] = merged["product_category_name_english"].fillna(
        merged["product_category_name"]
    )
    return merged.rename(columns={"product_photos_qty": "photos_qty"})[
        ["product_id", "category_name", "photos_qty", "product_weight_g"]
    ]


def build_dim_sellers(sellers: pd.DataFrame) -> pd.DataFrame:
    return sellers.rename(
        columns={
            "seller_zip_code_prefix": "zip_code_prefix",
        }
    )[["seller_id", "seller_city", "seller_state", "zip_code_prefix"]]


def build_dim_reviews(reviews: pd.DataFrame) -> pd.DataFrame:
    return reviews.rename(columns={"review_creation_date": "created_at"})[
        ["review_id", "order_id", "review_score", "created_at"]
    ]


def build_fact_orders(
    orders: pd.DataFrame,
    items: pd.DataFrame,
    payments: pd.DataFrame,
) -> pd.DataFrame:
    """
    Grain = one row per (order_id, order_item_id).

    Revenue per line item = price + freight_value  (we expose both the line
    revenue and the freight separately so the semantic layer can tell the LLM
    which to use for GMV vs shipping-cost questions).

    Payments are at the ORDER level, not the item level, so we DON'T join the
    raw payment_value onto every line (that would double-count). Instead we
    attach the dominant payment_type per order as a descriptive attribute.
    """
    # dominant payment type per order (mode of payment_type)
    pay_type = (
        payments.groupby("order_id")["payment_type"]
        .agg(lambda s: s.mode().iat[0] if not s.mode().empty else None)
        .reset_index()
        .rename(columns={"payment_type": "payment_type"})
    )

    fact = items.merge(
        orders[["order_id", "customer_id", "order_status", "order_purchase_timestamp"]],
        on="order_id",
        how="left",
    ).merge(pay_type, on="order_id", how="left")

    fact["order_total_usd"] = fact["price"] + fact["freight_value"]

    fact = fact.rename(
        columns={
            "customer_id": "user_id",
            "freight_value": "freight_value_usd",
            "order_purchase_timestamp": "created_at",
        }
    )
    return fact[
        [
            "order_id",
            "order_item_id",
            "user_id",
            "product_id",
            "seller_id",
            "order_status",
            "order_total_usd",
            "freight_value_usd",
            "payment_type",
            "created_at",
        ]
    ]


def main():
    os.makedirs("data", exist_ok=True)

    print("Reading raw CSVs from:", os.path.abspath(RAW_DIR))
    customers = _read("olist_customers_dataset")
    geo = _read("olist_geolocation_dataset")
    orders = _read("olist_orders_dataset")
    items = _read("olist_order_items_dataset")
    payments = _read("olist_order_payments_dataset")
    reviews = _read("olist_order_reviews_dataset")
    products = _read("olist_products_dataset")
    sellers = _read("olist_sellers_dataset")
    translation = _read("product_category_name_translation")

    print("Building star schema...")
    dim_geography = build_dim_geography(geo)
    dim_users = build_dim_users(customers)
    dim_products = build_dim_products(products, translation)
    dim_sellers = build_dim_sellers(sellers)
    dim_reviews = build_dim_reviews(reviews)
    fact_orders = build_fact_orders(orders, items, payments)

    engine = create_engine(f"sqlite:///{DB_PATH}")
    with engine.begin() as conn:
        fact_orders.to_sql("fact_orders", conn, if_exists="replace", index=False)
        dim_users.to_sql("dim_users", conn, if_exists="replace", index=False)
        dim_products.to_sql("dim_products", conn, if_exists="replace", index=False)
        dim_sellers.to_sql("dim_sellers", conn, if_exists="replace", index=False)
        dim_reviews.to_sql("dim_reviews", conn, if_exists="replace", index=False)
        dim_geography.to_sql("dim_geography", conn, if_exists="replace", index=False)
        # observability table for later phases
        conn.execute(text("DROP TABLE IF EXISTS query_log"))
        conn.execute(
            text(
                """
                CREATE TABLE query_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT,
                    generated_sql TEXT,
                    tables_used TEXT,
                    latency_ms INTEGER,
                    success INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    # quick summary
    with engine.connect() as conn:
        for t in [
            "fact_orders",
            "dim_users",
            "dim_products",
            "dim_sellers",
            "dim_reviews",
            "dim_geography",
        ]:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t:15s} {n:>10,} rows")

    print(f"\nDone. Database written to {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    main()
