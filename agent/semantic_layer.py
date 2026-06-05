"""
semantic_layer.py  --  The "data dictionary" the LLM reads before writing SQL.

The bare schema tells the model WHAT columns exist (names + types).
It does NOT tell the model how to USE them:
  - that order_total_usd is the revenue column (not freight_value_usd)
  - that fact_orders is one row per LINE ITEM, so count DISTINCT order_id
  - that user_id is per-ORDER but unique_id is per-PERSON  <-- broke our repeat-buyer query

This file encodes that domain knowledge. In Phase 3 we'll retrieve only the
RELEVANT entries per question (RAG); for now we inject all of them.

Each entry: a table description + notes on the columns that have non-obvious
business meaning. We don't need to annotate every column -- only the ones
where the name alone would mislead the model.
"""

SEMANTIC_LAYER = {
    "fact_orders": {
        "description": (
            "Central fact table. GRAIN = one row per ORDER LINE ITEM "
            "(an order with 3 products has 3 rows here). Because of this, "
            "to count ORDERS you MUST use COUNT(DISTINCT order_id), never "
            "COUNT(*) or COUNT(order_id), which counts line items and "
            "over-counts."
        ),
        "columns": {
            "order_id": "Order identifier. NOT unique in this table (repeats across line items). Use COUNT(DISTINCT order_id) to count orders.",
            "order_item_id": "Sequence number of the item within its order (1, 2, 3...).",
            "user_id": "Per-ORDER customer key. A given person gets a NEW user_id for every order they place, so this is NOT a stable person identifier. To identify a real person across orders, join to dim_users and use unique_id.",
            "product_id": "FK to dim_products.",
            "seller_id": "FK to dim_sellers.",
            "order_status": "Order state. Common values: 'delivered', 'shipped', 'canceled', 'unavailable', 'invoiced', 'processing'. Filter on 'delivered' for realized-sales/revenue questions unless asked otherwise.",
            "order_total_usd": "THE REVENUE COLUMN. Final line-item revenue (price + freight). ALWAYS use SUM(order_total_usd) for revenue / GMV / sales questions. NEVER use freight_value_usd as a revenue proxy.",
            "freight_value_usd": "Shipping cost only. Use ONLY for shipping/freight questions, never for revenue.",
            "payment_type": "Dominant payment method for the order: 'credit_card', 'boleto', 'voucher', 'debit_card'.",
            "created_at": "Order purchase timestamp stored as TEXT in 'YYYY-MM-DD HH:MM:SS' format. Use SQLite STRFTIME() to extract year/month, e.g. STRFTIME('%Y-%m', created_at).",
        },
    },
    "dim_users": {
        "description": (
            "Customer dimension. IMPORTANT: it has TWO id columns with very "
            "different meaning -- user_id (per-order) and unique_id (per-person)."
        ),
        "columns": {
            "user_id": "Per-ORDER customer key. Joins to fact_orders.user_id. NOT a stable person id.",
            "unique_id": "STABLE per-PERSON identifier. The SAME real customer shares one unique_id across all their orders. Use this (via COUNT(DISTINCT unique_id)) for repeat-buyer, retention, cohort, and unique-customer questions.",
            "city": "Customer city (lowercase).",
            "state": "CUSTOMER state, 2-letter Brazilian code (e.g. 'SP', 'RJ', 'MG'). This is the location an order COMES FROM. For questions about orders 'by state', 'from a state', or 'where orders/cancellations happen', use THIS column (the customer's state), NOT dim_sellers.seller_state.",
            "zip_code_prefix": "First digits of customer zip; joins to dim_geography.",
        },
    },
    "dim_products": {
        "description": "Product dimension. One row per product.",
        "columns": {
            "product_id": "PK. Joins to fact_orders.product_id.",
            "category_name": "Product category in ENGLISH (already translated from Portuguese). Use this for any 'by category' grouping.",
            "photos_qty": "Number of product photos in the listing.",
            "product_weight_g": "Product weight in grams.",
        },
    },
    "dim_sellers": {
        "description": "Seller (merchant) dimension. One row per seller.",
        "columns": {
            "seller_id": "PK. Joins to fact_orders.seller_id.",
            "seller_city": "Seller city (lowercase).",
            "seller_state": "SELLER (merchant) state, 2-letter code. Use ONLY when the question is explicitly about the SELLER's location or seller-side metrics (e.g. freight by seller state). For customer-origin questions, use dim_users.state instead.",
        },
    },
    "dim_reviews": {
        "description": (
            "Customer reviews, one row per review. Links to orders by order_id "
            "(NOT directly to sellers or products -- go through fact_orders for those)."
        ),
        "columns": {
            "review_id": "PK.",
            "order_id": "FK to the reviewed order. To attribute reviews to a seller or product, join dim_reviews -> fact_orders (on order_id) -> the relevant dimension.",
            "review_score": "Rating from 1 (worst) to 5 (best). Use AVG(review_score) for satisfaction / NPS-style questions.",
            "created_at": "Review creation date as TEXT 'YYYY-MM-DD'.",
        },
    },
    "dim_geography": {
        "description": "Geographic lookup, one row per zip prefix with representative lat/lng.",
        "columns": {
            "zip_code_prefix": "Joins to dim_users.zip_code_prefix or dim_sellers.zip_code_prefix.",
            "lat": "Representative latitude for the zip prefix.",
            "lng": "Representative longitude for the zip prefix.",
            "city": "City name (lowercase).",
            "state": "2-letter state code.",
        },
    },
}


def render_table(table_name: str) -> str:
    """Render one table's semantic description as prompt-ready text."""
    entry = SEMANTIC_LAYER[table_name]
    lines = [f"TABLE {table_name}", f"  Purpose: {entry['description']}", "  Columns:"]
    for col, desc in entry["columns"].items():
        lines.append(f"    - {col}: {desc}")
    return "\n".join(lines)


def render_all() -> str:
    """Render the full semantic layer (used in Phase 2; RAG replaces this in Phase 3)."""
    return "\n\n".join(render_table(t) for t in SEMANTIC_LAYER)


if __name__ == "__main__":
    print(render_all())