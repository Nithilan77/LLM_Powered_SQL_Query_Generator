"""
gold_olist.py  --  Hand-built evaluation set for the Olist database.

Each entry is a question + a GOLD SQL query that we have verified returns the
correct answer. The eval harness runs the system's predicted SQL and compares
its RESULT to the gold query's result (execution accuracy).

Fields:
  id            stable identifier
  question      natural-language question fed to the system
  gold_sql      the verified-correct SQL
  order_matters True if the SEQUENCE of rows is part of the answer
                (top-N / ranked questions). False for sets/aggregates.
  difficulty    easy | medium | hard  (for breakdown reporting)

IMPORTANT: gold_sql must be CORRECT. A wrong gold query silently makes a
correct prediction look "wrong". Every gold query is run + eyeballed before
being trusted (see verify_gold.py).

This starts at 10 to prove the harness; we expand to ~40 once it works.
"""

GOLD = [
    {
        "id": "q01_avg_review",
        "question": "What is the average review score across all reviews?",
        "gold_sql": "SELECT AVG(review_score) FROM dim_reviews",
        "order_matters": False,
        "difficulty": "easy",
    },
    {
        "id": "q02_total_revenue",
        "question": "What is the total revenue from delivered orders?",
        "gold_sql": (
            "SELECT SUM(order_total_usd) FROM fact_orders "
            "WHERE order_status = 'delivered'"
        ),
        "order_matters": False,
        "difficulty": "easy",
    },
    {
        "id": "q03_orders_by_status",
        "question": "How many distinct orders are there for each order status?",
        "gold_sql": (
            "SELECT order_status, COUNT(DISTINCT order_id) AS n "
            "FROM fact_orders GROUP BY order_status"
        ),
        "order_matters": False,
        "difficulty": "easy",
    },
    {
        "id": "q04_top5_categories_revenue",
        "question": "What are the top 5 product categories by total revenue from delivered orders?",
        "gold_sql": (
            "SELECT p.category_name, SUM(f.order_total_usd) AS revenue "
            "FROM fact_orders f JOIN dim_products p ON f.product_id = p.product_id "
            "WHERE f.order_status = 'delivered' "
            "GROUP BY p.category_name ORDER BY revenue DESC LIMIT 5"
        ),
        "order_matters": True,
        "difficulty": "medium",
    },
    {
        "id": "q05_canceled_by_state",
        "question": "Which 5 states have the most canceled orders?",
        "gold_sql": (
            "SELECT u.state, COUNT(DISTINCT f.order_id) AS canceled "
            "FROM fact_orders f JOIN dim_users u ON f.user_id = u.user_id "
            "WHERE f.order_status = 'canceled' "
            "GROUP BY u.state ORDER BY canceled DESC LIMIT 5"
        ),
        "order_matters": True,
        "difficulty": "medium",
    },
    {
        "id": "q06_repeat_buyers",
        "question": "How many customers are repeat buyers (more than one order)?",
        "gold_sql": (
            "SELECT COUNT(*) FROM ("
            "  SELECT u.unique_id FROM fact_orders f "
            "  JOIN dim_users u ON f.user_id = u.user_id "
            "  GROUP BY u.unique_id HAVING COUNT(DISTINCT f.order_id) > 1"
            ")"
        ),
        "order_matters": False,
        "difficulty": "hard",
    },
    {
        "id": "q07_monthly_revenue_2018",
        "question": "What is the total delivered revenue for each month of 2018?",
        "gold_sql": (
            "SELECT STRFTIME('%Y-%m', created_at) AS month, "
            "SUM(order_total_usd) AS revenue "
            "FROM fact_orders "
            "WHERE order_status = 'delivered' AND STRFTIME('%Y', created_at) = '2018' "
            "GROUP BY month ORDER BY month"
        ),
        "order_matters": True,
        "difficulty": "medium",
    },
    {
        "id": "q08_top_sellers_by_review",
        "question": "Which 5 sellers have the highest average review score, considering only sellers with at least 50 reviews?",
        "gold_sql": (
            "SELECT s.seller_id, AVG(r.review_score) AS avg_score "
            "FROM dim_sellers s "
            "JOIN fact_orders f ON s.seller_id = f.seller_id "
            "JOIN dim_reviews r ON f.order_id = r.order_id "
            "GROUP BY s.seller_id HAVING COUNT(r.review_id) >= 50 "
            "ORDER BY avg_score DESC LIMIT 5"
        ),
        "order_matters": True,
        "difficulty": "hard",
    },
    {
        "id": "q09_avg_freight_by_state",
        "question": "What is the average freight value per seller state, for the top 5 states by average freight?",
        "gold_sql": (
            "SELECT s.seller_state, AVG(f.freight_value_usd) AS avg_freight "
            "FROM fact_orders f JOIN dim_sellers s ON f.seller_id = s.seller_id "
            "GROUP BY s.seller_state ORDER BY avg_freight DESC LIMIT 5"
        ),
        "order_matters": True,
        "difficulty": "medium",
    },
    {
        "id": "q10_pct_delivered",
        "question": "How many distinct orders were delivered?",
        "gold_sql": (
            "SELECT COUNT(DISTINCT order_id) FROM fact_orders "
            "WHERE order_status = 'delivered'"
        ),
        "order_matters": False,
        "difficulty": "easy",
    },
]