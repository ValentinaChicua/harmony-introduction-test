from typing import Any, List


# ---------------------------------------------------------------------------
# Query 1 — Active users and their order count
# ---------------------------------------------------------------------------

def query_1_get_active_users_with_orders(db: Any) -> List[dict]:
    """
    Retrieve active users together with their total number of orders.
    Optimized using a single aggregated query.
    """

    query = """
        SELECT
            u.id,
            u.email,
            u.name,
            u.status,
            u.created_at,
            COUNT(o.id) AS order_count
        FROM users u
        LEFT JOIN orders o
            ON o.user_id = u.id
        WHERE u.status = %s
        GROUP BY
            u.id,
            u.email,
            u.name,
            u.status,
            u.created_at
        ORDER BY order_count DESC
    """

    rows = db.execute(query, ("active",)).fetchall()

    return [
        {
            "user": {
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "status": row["status"],
                "created_at": row["created_at"],
            },
            "order_count": row["order_count"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Query 2 — Top-selling products
# ---------------------------------------------------------------------------

def query_2_top_selling_products(db: Any) -> List[dict]:
    """
    Return the 10 products with the highest revenue from paid orders.
    Optimized using grouped joins instead of correlated subqueries.
    """

    query = """
        SELECT
            p.id,
            p.name,
            c.name AS category_name,
            SUM(oi.quantity * oi.unit_price) AS total_revenue
        FROM order_items oi
        INNER JOIN orders o
            ON o.id = oi.order_id
           AND o.status = %s
        INNER JOIN products p
            ON p.id = oi.product_id
        INNER JOIN categories c
            ON c.id = p.category_id
        GROUP BY
            p.id,
            p.name,
            c.name
        ORDER BY total_revenue DESC
        LIMIT 10
    """

    rows = db.execute(query, ("paid",)).fetchall()

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Query 3 — Users who purchased from a specific category
# ---------------------------------------------------------------------------

def query_3_users_who_purchased_category(
    db: Any,
    category_name: str
) -> List[dict]:
    """
    Return active users who purchased at least one product
    from the specified category.
    """

    query = """
        SELECT DISTINCT
            u.email,
            u.name
        FROM users u
        INNER JOIN orders o
            ON o.user_id = u.id
           AND o.status = %s
        INNER JOIN order_items oi
            ON oi.order_id = o.id
        INNER JOIN products p
            ON p.id = oi.product_id
        INNER JOIN categories c
            ON c.id = p.category_id
        WHERE u.status = %s
          AND c.name = %s
    """

    rows = db.execute(
        query,
        ("paid", "active", category_name)
    ).fetchall()

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Query 4 — Product keyword search
# ---------------------------------------------------------------------------

def query_4_search_products_by_keyword(
    db: Any,
    keyword: str
) -> List[dict]:
    """
    Full-text search for products by keyword.
    Uses FULLTEXT indexes for scalability.
    """

    query = """
        SELECT
            p.id,
            p.name,
            p.description,
            p.price,
            p.stock,
            c.name AS category_name
        FROM products p
        INNER JOIN categories c
            ON c.id = p.category_id
        WHERE
            MATCH(p.name, p.description)
            AGAINST (%s IN NATURAL LANGUAGE MODE)
        ORDER BY p.price ASC
    """

    rows = db.execute(query, (keyword,)).fetchall()

    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Query 5 — Monthly revenue report
# ---------------------------------------------------------------------------

def query_5_monthly_revenue_report(
    db: Any,
    page: int = 1,
    page_size: int = 12
) -> List[dict]:
    """
    Compute monthly revenue for the last 12 months.
    Optimized grouping and parameterized pagination.
    """

    offset = (page - 1) * page_size

    query = """
        SELECT
            YEAR(o.created_at) AS year,
            MONTH(o.created_at) AS month,
            SUM(o.total) AS revenue
        FROM orders o
        WHERE o.status = %s
          AND o.created_at >= CURRENT_DATE - INTERVAL 12 MONTH
        GROUP BY
            YEAR(o.created_at),
            MONTH(o.created_at)
        ORDER BY
            year DESC,
            month DESC
        LIMIT %s OFFSET %s
    """

    rows = db.execute(
        query,
        ("paid", page_size, offset)
    ).fetchall()

    return [
        {
            "month": f"{row['year']}-{row['month']:02d}",
            "revenue": row["revenue"],
        }
        for row in rows
    ]