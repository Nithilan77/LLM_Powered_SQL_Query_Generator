"""
gold_olist.py  --  Hand-built evaluation set for the Olist database (40 questions).

Each entry: id, question, gold_sql, order_matters, difficulty.
The harness compares the system's predicted RESULT to the gold query's result
(execution accuracy). Every gold query is verified with verify_gold.py before use.

Coverage spans: simple aggregates, grouped aggregates, top-N rankings, multi-hop
joins, time-series, payment analysis, geography, freight, customer cohorts, and
a few deliberately HARD questions the system may fail (honest eval, not cherry-picked).
"""

GOLD = [
    # ---------------- easy: single-table aggregates ----------------
    {"id": "q01_avg_review", "question": "What is the average review score across all reviews?",
     "gold_sql": "SELECT AVG(review_score) FROM dim_reviews", "order_matters": False, "difficulty": "easy"},
    {"id": "q02_total_revenue", "question": "What is the total revenue from delivered orders?",
     "gold_sql": "SELECT SUM(order_total_usd) FROM fact_orders WHERE order_status = 'delivered'", "order_matters": False, "difficulty": "easy"},
    {"id": "q03_orders_by_status", "question": "How many distinct orders are there for each order status?",
     "gold_sql": "SELECT order_status, COUNT(DISTINCT order_id) AS n FROM fact_orders GROUP BY order_status", "order_matters": False, "difficulty": "easy"},
    {"id": "q10_delivered_count", "question": "How many distinct orders were delivered?",
     "gold_sql": "SELECT COUNT(DISTINCT order_id) FROM fact_orders WHERE order_status = 'delivered'", "order_matters": False, "difficulty": "easy"},
    {"id": "q11_distinct_sellers", "question": "How many distinct sellers are there?",
     "gold_sql": "SELECT COUNT(*) FROM dim_sellers", "order_matters": False, "difficulty": "easy"},
    {"id": "q12_distinct_products", "question": "How many distinct products exist in the catalog?",
     "gold_sql": "SELECT COUNT(*) FROM dim_products", "order_matters": False, "difficulty": "easy"},
    {"id": "q13_total_freight", "question": "What is the total freight value across all order line items?",
     "gold_sql": "SELECT SUM(freight_value_usd) FROM fact_orders", "order_matters": False, "difficulty": "easy"},
    {"id": "q14_count_5star", "question": "How many reviews gave a perfect score of 5?",
     "gold_sql": "SELECT COUNT(*) FROM dim_reviews WHERE review_score = 5", "order_matters": False, "difficulty": "easy"},
    {"id": "q15_avg_order_value", "question": "What is the average line-item revenue (order_total_usd) across all rows?",
     "gold_sql": "SELECT AVG(order_total_usd) FROM fact_orders", "order_matters": False, "difficulty": "easy"},
    {"id": "q16_distinct_categories", "question": "How many distinct product categories are there?",
     "gold_sql": "SELECT COUNT(DISTINCT category_name) FROM dim_products", "order_matters": False, "difficulty": "easy"},

    # ---------------- medium: joins, group-by, top-N ----------------
    {"id": "q04_top5_categories_revenue", "question": "What are the top 5 product categories by total revenue from delivered orders?",
     "gold_sql": "SELECT p.category_name, SUM(f.order_total_usd) AS revenue FROM fact_orders f JOIN dim_products p ON f.product_id = p.product_id WHERE f.order_status = 'delivered' GROUP BY p.category_name ORDER BY revenue DESC LIMIT 5", "order_matters": True, "difficulty": "medium"},
    {"id": "q05_canceled_by_state", "question": "Which 5 states have the most canceled orders? Use the customer's state.",
     "gold_sql": "SELECT u.state, COUNT(DISTINCT f.order_id) AS canceled FROM fact_orders f JOIN dim_users u ON f.user_id = u.user_id WHERE f.order_status = 'canceled' GROUP BY u.state ORDER BY canceled DESC LIMIT 5", "order_matters": True, "difficulty": "medium"},
    {"id": "q07_monthly_revenue_2018", "question": "What is the total delivered revenue for each month of 2018?",
     "gold_sql": "SELECT STRFTIME('%Y-%m', created_at) AS month, SUM(order_total_usd) AS revenue FROM fact_orders WHERE order_status = 'delivered' AND STRFTIME('%Y', created_at) = '2018' GROUP BY month ORDER BY month", "order_matters": True, "difficulty": "medium"},
    {"id": "q09_top5_freight_seller_state", "question": "Across all orders (regardless of status), what is the average freight value per seller state? Return the top 5 states by average freight.",
     "gold_sql": "SELECT s.seller_state, AVG(f.freight_value_usd) AS avg_freight FROM fact_orders f JOIN dim_sellers s ON f.seller_id = s.seller_id GROUP BY s.seller_state ORDER BY avg_freight DESC LIMIT 5", "order_matters": True, "difficulty": "medium"},
    {"id": "q17_payment_type_breakdown", "question": "How many distinct orders used each payment type?",
     "gold_sql": "SELECT payment_type, COUNT(DISTINCT order_id) AS n FROM fact_orders GROUP BY payment_type", "order_matters": False, "difficulty": "medium"},
    {"id": "q18_top_customer_states_by_orders", "question": "Which 10 customer states placed the most distinct orders?",
     "gold_sql": "SELECT u.state, COUNT(DISTINCT f.order_id) AS orders FROM fact_orders f JOIN dim_users u ON f.user_id = u.user_id GROUP BY u.state ORDER BY orders DESC LIMIT 10", "order_matters": True, "difficulty": "medium"},
    {"id": "q19_revenue_by_state", "question": "What is the total delivered revenue per customer state, for the top 5 states?",
     "gold_sql": "SELECT u.state, SUM(f.order_total_usd) AS revenue FROM fact_orders f JOIN dim_users u ON f.user_id = u.user_id WHERE f.order_status = 'delivered' GROUP BY u.state ORDER BY revenue DESC LIMIT 5", "order_matters": True, "difficulty": "medium"},
    {"id": "q20_avg_review_by_category", "question": "What are the 5 product categories with the highest average review score (minimum 100 reviews)?",
     "gold_sql": "SELECT p.category_name, AVG(r.review_score) AS avg_score FROM dim_reviews r JOIN fact_orders f ON r.order_id = f.order_id JOIN dim_products p ON f.product_id = p.product_id GROUP BY p.category_name HAVING COUNT(r.review_id) >= 100 ORDER BY avg_score DESC LIMIT 5", "order_matters": True, "difficulty": "hard"},
    {"id": "q21_worst_categories_review", "question": "Which 5 product categories have the lowest average review score (minimum 100 reviews)?",
     "gold_sql": "SELECT p.category_name, AVG(r.review_score) AS avg_score FROM dim_reviews r JOIN fact_orders f ON r.order_id = f.order_id JOIN dim_products p ON f.product_id = p.product_id GROUP BY p.category_name HAVING COUNT(r.review_id) >= 100 ORDER BY avg_score ASC LIMIT 5", "order_matters": True, "difficulty": "hard"},
    {"id": "q22_orders_per_month_2017", "question": "How many distinct orders were placed in each month of 2017?",
     "gold_sql": "SELECT STRFTIME('%Y-%m', created_at) AS month, COUNT(DISTINCT order_id) AS orders FROM fact_orders WHERE STRFTIME('%Y', created_at) = '2017' GROUP BY month ORDER BY month", "order_matters": True, "difficulty": "medium"},
    {"id": "q23_top_sellers_by_revenue", "question": "Which 10 sellers generated the most delivered revenue?",
     "gold_sql": "SELECT seller_id, SUM(order_total_usd) AS revenue FROM fact_orders WHERE order_status = 'delivered' GROUP BY seller_id ORDER BY revenue DESC LIMIT 10", "order_matters": True, "difficulty": "medium"},
    {"id": "q24_avg_freight_by_category", "question": "What is the average freight value for the top 5 product categories by freight?",
     "gold_sql": "SELECT p.category_name, AVG(f.freight_value_usd) AS avg_freight FROM fact_orders f JOIN dim_products p ON f.product_id = p.product_id GROUP BY p.category_name ORDER BY avg_freight DESC LIMIT 5", "order_matters": True, "difficulty": "medium"},
    {"id": "q25_pct_5star", "question": "What percentage of all reviews are 5-star? Return a single percentage value.",
     "gold_sql": "SELECT 100.0 * SUM(CASE WHEN review_score = 5 THEN 1 ELSE 0 END) / COUNT(*) FROM dim_reviews", "order_matters": False, "difficulty": "medium"},
    {"id": "q26_sellers_per_state", "question": "How many sellers are based in each seller state, for the top 5 states?",
     "gold_sql": "SELECT seller_state, COUNT(*) AS n FROM dim_sellers GROUP BY seller_state ORDER BY n DESC LIMIT 5", "order_matters": True, "difficulty": "medium"},
    {"id": "q27_avg_items_per_order", "question": "What is the average number of line items per order?",
     "gold_sql": "SELECT AVG(item_count) FROM (SELECT order_id, COUNT(*) AS item_count FROM fact_orders GROUP BY order_id)", "order_matters": False, "difficulty": "hard"},
    {"id": "q28_customers_per_state", "question": "How many distinct customers (by unique_id) are in each of the top 5 states?",
     "gold_sql": "SELECT state, COUNT(DISTINCT unique_id) AS customers FROM dim_users GROUP BY state ORDER BY customers DESC LIMIT 5", "order_matters": True, "difficulty": "medium"},
    {"id": "q29_revenue_credit_card", "question": "What is the total delivered revenue from orders paid by credit card?",
     "gold_sql": "SELECT SUM(order_total_usd) FROM fact_orders WHERE order_status = 'delivered' AND payment_type = 'credit_card'", "order_matters": False, "difficulty": "medium"},
    {"id": "q30_top_products_by_orders", "question": "Which 10 products appear in the most distinct orders?",
     "gold_sql": "SELECT product_id, COUNT(DISTINCT order_id) AS orders FROM fact_orders GROUP BY product_id ORDER BY orders DESC LIMIT 10", "order_matters": True, "difficulty": "medium"},

    # ---------------- hard: multi-step, cohorts, ratios ----------------
    {"id": "q06_repeat_buyers", "question": "What is the total number of repeat-buyer customers, where a repeat buyer is a person (unique_id) who placed more than one distinct order? Return a single count.",
     "gold_sql": "SELECT COUNT(*) FROM (SELECT u.unique_id FROM fact_orders f JOIN dim_users u ON f.user_id = u.user_id GROUP BY u.unique_id HAVING COUNT(DISTINCT f.order_id) > 1)", "order_matters": False, "difficulty": "hard"},
    {"id": "q08_top_sellers_by_review", "question": "Which 5 sellers have the highest average review score, considering only sellers with at least 50 reviews?",
     "gold_sql": "SELECT s.seller_id, AVG(r.review_score) AS avg_score FROM dim_sellers s JOIN fact_orders f ON s.seller_id = f.seller_id JOIN dim_reviews r ON f.order_id = r.order_id GROUP BY s.seller_id HAVING COUNT(r.review_id) >= 50 ORDER BY avg_score DESC LIMIT 5", "order_matters": True, "difficulty": "hard"},
    {"id": "q31_cancel_rate", "question": "What is the overall cancellation rate as a percentage of distinct orders? Return a single value.",
     "gold_sql": "SELECT 100.0 * COUNT(DISTINCT CASE WHEN order_status = 'canceled' THEN order_id END) / COUNT(DISTINCT order_id) FROM fact_orders", "order_matters": False, "difficulty": "hard"},
    {"id": "q32_max_monthly_revenue", "question": "What is the highest single-month delivered revenue across all months and years?",
     "gold_sql": "SELECT MAX(monthly) FROM (SELECT STRFTIME('%Y-%m', created_at) AS m, SUM(order_total_usd) AS monthly FROM fact_orders WHERE order_status = 'delivered' GROUP BY m)", "order_matters": False, "difficulty": "hard"},
    {"id": "q33_category_with_most_sellers", "question": "Which 5 product categories are sold by the most distinct sellers?",
     "gold_sql": "SELECT p.category_name, COUNT(DISTINCT f.seller_id) AS sellers FROM fact_orders f JOIN dim_products p ON f.product_id = p.product_id GROUP BY p.category_name ORDER BY sellers DESC LIMIT 5", "order_matters": True, "difficulty": "hard"},
    {"id": "q34_state_highest_avg_review", "question": "Which customer state has the highest average review score, among states with at least 500 reviews? Return the single top state.",
     "gold_sql": "SELECT u.state, AVG(r.review_score) AS avg_score FROM dim_reviews r JOIN fact_orders f ON r.order_id = f.order_id JOIN dim_users u ON f.user_id = u.user_id GROUP BY u.state HAVING COUNT(r.review_id) >= 500 ORDER BY avg_score DESC LIMIT 1", "order_matters": True, "difficulty": "hard"},
    {"id": "q35_freight_pct_revenue", "question": "Across delivered orders, what is total freight as a percentage of total revenue? Return a single value.",
     "gold_sql": "SELECT 100.0 * SUM(freight_value_usd) / SUM(order_total_usd) FROM fact_orders WHERE order_status = 'delivered'", "order_matters": False, "difficulty": "hard"},
    {"id": "q36_yearly_revenue", "question": "What is the total delivered revenue for each year?",
     "gold_sql": "SELECT STRFTIME('%Y', created_at) AS year, SUM(order_total_usd) AS revenue FROM fact_orders WHERE order_status = 'delivered' GROUP BY year ORDER BY year", "order_matters": True, "difficulty": "medium"},
    {"id": "q37_single_order_customers", "question": "How many customers (unique_id) placed exactly one distinct order? Return a single count.",
     "gold_sql": "SELECT COUNT(*) FROM (SELECT u.unique_id FROM fact_orders f JOIN dim_users u ON f.user_id = u.user_id GROUP BY u.unique_id HAVING COUNT(DISTINCT f.order_id) = 1)", "order_matters": False, "difficulty": "hard"},
    {"id": "q38_top_category_by_volume", "question": "Which product category appears in the most distinct orders? Return the single top category.",
     "gold_sql": "SELECT p.category_name, COUNT(DISTINCT f.order_id) AS orders FROM fact_orders f JOIN dim_products p ON f.product_id = p.product_id GROUP BY p.category_name ORDER BY orders DESC LIMIT 1", "order_matters": True, "difficulty": "medium"},
    {"id": "q39_boleto_share", "question": "What percentage of distinct orders were paid using boleto? Return a single value.",
     "gold_sql": "SELECT 100.0 * COUNT(DISTINCT CASE WHEN payment_type = 'boleto' THEN order_id END) / COUNT(DISTINCT order_id) FROM fact_orders", "order_matters": False, "difficulty": "hard"},
    {"id": "q40_avg_score_by_payment", "question": "What is the average review score for orders grouped by payment type?",
     "gold_sql": "SELECT f.payment_type, AVG(r.review_score) AS avg_score FROM dim_reviews r JOIN fact_orders f ON r.order_id = f.order_id GROUP BY f.payment_type", "order_matters": False, "difficulty": "hard"},
]