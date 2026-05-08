# admin/admin_routes.py
#
# PREREQUISITES:
#   1. Insert the static admin user into auth.app_users (run once in psql).
#      Password below is 123456 (bcrypt). Regenerate:  python -c "import bcrypt; print(bcrypt.hashpw(b'123456', bcrypt.gensalt()).decode())"
#
#      INSERT INTO auth.app_users (full_name, email, password_hash, is_active)
#      VALUES (
#          'Admin',
#          'admin@gmail.com',
#          '$2b$12$Eo95xPLEWWchxWTZnltOO.S2GXyzR9xZ0BmZXF4XSxz.YsdV2ni26',
#          TRUE
#      )
#      ON CONFLICT (email) DO NOTHING;

import os
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

from groq import Groq
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from auth.auth_routes import get_current_user
from infrastructure.db import SQL_ENGINE

router = APIRouter(prefix="/admin", tags=["Admin"])

# ─── Static admin identity ───────────────────────────────────────────────────
ADMIN_EMAIL = "admin@gmail.com"

# ─── Groq client ─────────────────────────────────────────────────────────────
_GROQ_KEY = os.getenv("GROQ_API2_KEY", "")
_groq_client = Groq(api_key=_GROQ_KEY) if _GROQ_KEY else None


# ─── Admin guard ─────────────────────────────────────────────────────────────

def _require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency: allows access only to the static admin account."""
    if current_user.get("email") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/orders")
def get_recent_orders(days: int = 7, _: Dict = Depends(_require_admin)):
    """
    Fetch all recent orders within the last X days.
    Includes customer name, aggregated item strings, order total, status, and feedback review.
    """
    try:
        with SQL_ENGINE.begin() as conn:
            query = text("""
                SELECT 
                    o.order_id,
                    o.order_type,
                    COALESCE(
                        u.full_name,
                        CASE
                            WHEN COALESCE(o.order_type, 'delivery') = 'dine_in' THEN CONCAT('Table ', rt.table_number)
                            ELSE NULL
                        END,
                        'Guest'
                    ) AS customer_name,
                    o.total_price AS total,
                    o.status,
                    o.created_at,
                    f.rating AS review_rating,
                    f.message AS review_text,
                    (
                        SELECT string_agg(oi.name_snapshot || ' x' || oi.quantity::text, ', ')
                        FROM public.order_items oi
                        WHERE oi.order_id = o.order_id
                    ) AS items_str
                FROM public.orders o
                LEFT JOIN public.cart c ON o.cart_id = c.cart_id
                LEFT JOIN auth.app_users u ON c.user_id = u.user_id
                LEFT JOIN public.dine_in_sessions s ON s.session_id = o.session_id
                LEFT JOIN public.restaurant_tables rt ON rt.table_id = s.table_id
                LEFT JOIN public.feedback f ON f.order_id = o.order_id AND f.item_id IS NULL AND f.feedback_type = 'ORDER'
                WHERE o.created_at >= NOW() - INTERVAL '1 day' * :days
                ORDER BY o.created_at DESC
            """)
            
            rows = conn.execute(query, {"days": days}).mappings().fetchall()
            
            orders = []
            for r in rows:
                items_list = []
                if r["items_str"]:
                    items_list = [i.strip() for i in str(r["items_str"]).split(",") if i.strip()]
                    
                orders.append({
                    "order_id": r["order_id"],
                    "customer_name": r["customer_name"] or "Guest",
                    "order_type": (r["order_type"] or "delivery"),
                    "items": items_list,
                    "total": float(r["total"] or 0.0),
                    "status": r["status"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "review_rating": r["review_rating"],
                    "review_text": r["review_text"],
                })
                
            return {"orders": orders}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to fetch recent orders")


# ─── Helper ──────────────────────────────────────────────────────────────────

def _float(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _int(val, default: int = 0) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _normalize_item_category(raw_category: str) -> str:
    """Map UI/category aliases to canonical menu_item.item_category values."""
    category = (raw_category or "").strip().lower()
    aliases = {
        "sides": "side",
        "side": "side",
        "starters": "starter",
        "starter": "starter",
        "drinks": "drink",
        "drink": "drink",
        "mains": "main",
        "main": "main",
        "bread": "bread",
        "all": "all",
    }
    return aliases.get(category, category)


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/overview
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/overview")
def admin_overview(_: Dict = Depends(_require_admin)):
    """
    Returns today's key metrics:
      today_orders, today_revenue, avg_order_value, active_orders,
      revenue_delta, orders_delta, aov_delta,
      revenue_chart_data, category_sales_data
    """
    with SQL_ENGINE.connect() as conn:
        today_row = conn.execute(
            text("""
                SELECT
                    COUNT(*)                              AS today_orders,
                    COALESCE(SUM(total_price), 0)         AS today_revenue,
                    COALESCE(AVG(total_price), 0)         AS avg_order_value
                FROM orders
                WHERE DATE(created_at AT TIME ZONE 'Asia/Karachi') = CURRENT_DATE
                  AND status NOT IN ('cancelled', 'declined')
            """)
        ).mappings().fetchone()

        yesterday_row = conn.execute(
            text("""
                SELECT
                    COUNT(*)                              AS yesterday_orders,
                    COALESCE(SUM(total_price), 0)         AS yesterday_revenue,
                    COALESCE(AVG(total_price), 0)         AS yesterday_aov
                FROM orders
                WHERE DATE(created_at AT TIME ZONE 'Asia/Karachi') = CURRENT_DATE - INTERVAL '1 day'
                  AND status NOT IN ('cancelled', 'declined')
            """)
        ).mappings().fetchone()

        active_row = conn.execute(
            text("""
                SELECT COUNT(*) AS active_orders
                FROM orders
                WHERE status NOT IN ('cancelled', 'completed')
            """)
        ).mappings().fetchone()

        # 7 days revenue for line chart
        revenue_chart_rows = conn.execute(
            text("""
                SELECT 
                    TO_CHAR(DATE(created_at AT TIME ZONE 'Asia/Karachi'), 'Mon DD') as day_label,
                    SUM(total_price) as daily_revenue
                FROM orders
                WHERE created_at >= NOW() - INTERVAL '6 days'
                  AND status NOT IN ('cancelled', 'declined')
                GROUP BY DATE(created_at AT TIME ZONE 'Asia/Karachi')
                ORDER BY DATE(created_at AT TIME ZONE 'Asia/Karachi') ASC
            """)
        ).mappings().fetchall()

        # Category distribution for donut chart
        category_rows = conn.execute(
            text("""
                SELECT 
                    CASE
                        WHEN oi.item_type = 'deal' THEN 'Deals'
                        WHEN oi.item_type = 'custom_deal' THEN 'Custom Deals'
                        ELSE COALESCE(mi.item_category, 'Other')
                    END as category_name,
                    SUM(oi.quantity * oi.unit_price_snapshot) as category_revenue
                FROM order_items oi
                JOIN orders o ON o.order_id = oi.order_id
                LEFT JOIN menu_item mi ON mi.item_id = oi.item_id AND oi.item_type = 'menu_item'
                WHERE o.status NOT IN ('cancelled', 'declined')
                GROUP BY category_name
                ORDER BY category_revenue DESC
            """)
        ).mappings().fetchall()

    revenue_chart_data = [
        {"day": row["day_label"], "revenue": round(_float(row["daily_revenue"]), 2)}
        for row in revenue_chart_rows
    ]
    
    category_sales_data = [
        {"category": row["category_name"], "revenue": round(_float(row["category_revenue"]), 2)}
        for row in category_rows
    ]

    t_orders = _int(today_row["today_orders"])
    t_rev = _float(today_row["today_revenue"])
    t_aov = _float(today_row["avg_order_value"])

    y_orders = _int(yesterday_row["yesterday_orders"])
    y_rev = _float(yesterday_row["yesterday_revenue"])
    y_aov = _float(yesterday_row["yesterday_aov"])

    def calc_delta(today_val: float, yesterday_val: float) -> float:
        if yesterday_val == 0:
            return 100.0 if today_val > 0 else 0.0
        return ((today_val - yesterday_val) / yesterday_val) * 100.0

    return {
        "today_orders":    t_orders,
        "today_revenue":   round(t_rev, 2),
        "avg_order_value": round(t_aov, 2),
        "active_orders":   _int(active_row["active_orders"]),
        "orders_delta":    round(calc_delta(t_orders, y_orders), 1),
        "revenue_delta":   round(calc_delta(t_rev, y_rev), 1),
        "aov_delta":       round(calc_delta(t_aov, y_aov), 1),
        "revenue_chart_data": revenue_chart_data,
        "category_sales_data": category_sales_data,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/revenue?period=30&category=all
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/revenue")
def admin_revenue(
    period:   int = Query(default=30, ge=1, le=365, description="Number of past days"),
    category: str = Query(default="all", description="Item category filter or 'all'"),
    _: Dict = Depends(_require_admin),
):
    """
    Aggregated revenue & profit for the given period.
    profit is estimated as 30 % of revenue (cost data not stored).

    Returns:
      total_orders, total_revenue, total_profit, aov,
      daily_data: [{date, revenue, profit}]
    """
    # Build optional category join clause
    cat_filter = ""
    params: Dict[str, Any] = {"days": period}
    normalized_category = _normalize_item_category(category)
    if normalized_category and normalized_category != "all":
        cat_filter = """
            AND o.order_id IN (
                SELECT DISTINCT oi.order_id
                FROM order_items oi
                JOIN menu_item mi ON mi.item_id = oi.item_id
                   AND oi.item_type = 'menu_item'
                WHERE LOWER(mi.item_category) = :category
            )
        """
        params["category"] = normalized_category

    summary_sql = text(f"""
        SELECT
            COUNT(*)                      AS total_orders,
            COALESCE(SUM(total_price), 0) AS total_revenue
        FROM orders o
        WHERE o.created_at >= NOW() - INTERVAL '1 day' * :days
          AND o.status NOT IN ('cancelled')
        {cat_filter}
    """)

    daily_sql = text(f"""
        WITH date_range AS (
            SELECT (CURRENT_DATE - (i || ' day')::interval)::date AS day
            FROM generate_series(0, :days - 1) AS i
        ),
        daily_revenue AS (
            SELECT
                DATE(o.created_at AT TIME ZONE 'Asia/Karachi') AS day,
                COALESCE(SUM(total_price), 0)                  AS revenue
            FROM orders o
            WHERE o.created_at >= NOW() - INTERVAL '1 day' * :days
              AND o.status NOT IN ('cancelled')
            {cat_filter}
            GROUP BY day
        )
        SELECT 
            dr.day,
            COALESCE(rev.revenue, 0) AS revenue
        FROM date_range dr
        LEFT JOIN daily_revenue rev ON rev.day = dr.day
        ORDER BY dr.day ASC
    """)

    with SQL_ENGINE.connect() as conn:
        summary = conn.execute(summary_sql, params).mappings().fetchone()
        daily_rows = conn.execute(daily_sql, params).mappings().all()

    total_orders  = _int(summary["total_orders"])
    total_revenue = round(_float(summary["total_revenue"]), 2)
    total_profit  = round(total_revenue * 0.30, 2)   # 30 % margin estimate
    aov = round(total_revenue / total_orders, 2) if total_orders else 0.0

    daily_data = [
        {
            "date":    str(r["day"]),
            "revenue": round(_float(r["revenue"]), 2),
            "profit":  round(_float(r["revenue"]) * 0.30, 2),
        }
        for r in daily_rows
    ]

    return {
        "total_orders":  total_orders,
        "total_revenue": total_revenue,
        "total_profit":  total_profit,
        "aov":           aov,
        "daily_data":    daily_data,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/trends?period=30
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/trends")
def admin_trends(
    period: int = Query(default=30, ge=1, le=365, description="Number of past days"),
    _: Dict = Depends(_require_admin),
):
    """
    Returns:
      top_items:   [{rank, name, units_sold, revenue}]  (top 10, menu items + deals)
      low_items:   [{rank, name, units_sold, revenue}]  (bottom 10, includes zero-sales)
      hourly_data: [{hour, avg_orders}]
    """
    window_filter = "o.created_at >= NOW() - INTERVAL '1 day' * :days"
    params = {"days": period}

    # Build sales over a full catalog (menu items + deals) so low_items can include zero-sales entries.
    catalog_sales_sql = text(f"""
        WITH catalog AS (
            SELECT
                'menu_item'::text AS item_type,
                mi.item_id        AS item_id,
                mi.item_name      AS name
            FROM menu_item mi

            UNION ALL

            SELECT
                'deal'::text      AS item_type,
                d.deal_id         AS item_id,
                d.deal_name       AS name
            FROM deal d
        ),
        sales AS (
            SELECT
                oi.item_type::text               AS item_type,
                oi.item_id                       AS item_id,
                SUM(oi.quantity)                 AS units_sold,
                COALESCE(SUM(oi.line_total), 0)  AS revenue
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id
            WHERE {window_filter}
              AND o.status NOT IN ('cancelled')
              AND oi.item_type IN ('menu_item', 'deal')
            GROUP BY oi.item_type, oi.item_id
        )
        SELECT
            c.name,
            COALESCE(s.units_sold, 0) AS units_sold,
            COALESCE(s.revenue, 0)    AS revenue
        FROM catalog c
        LEFT JOIN sales s
          ON s.item_type = c.item_type
         AND s.item_id = c.item_id
    """)

    hourly_sql = text(f"""
        SELECT
            EXTRACT(HOUR FROM o.created_at AT TIME ZONE 'Asia/Karachi')::int AS hour,
            COUNT(*)                                                           AS order_cnt
        FROM orders o
        WHERE {window_filter}
        GROUP BY hour
        ORDER BY hour ASC
    """)

    # Total distinct days for avg
    days_sql = text(f"""
        SELECT COUNT(DISTINCT DATE(created_at AT TIME ZONE 'Asia/Karachi')) AS total_days
        FROM orders o
        WHERE {window_filter}
    """)

    with SQL_ENGINE.connect() as conn:
        all_items = conn.execute(catalog_sales_sql, params).mappings().all()
        hourly_rows = conn.execute(hourly_sql, params).mappings().all()
        days_row = conn.execute(days_sql, params).mappings().fetchone()

    total_days = max(1, _int(days_row["total_days"]))

    # Sort once for top and once for low lists.
    top_sorted_items = sorted(
        all_items,
        key=lambda r: (-_int(r["units_sold"]), -_float(r["revenue"]), str(r["name"] or "").lower()),
    )
    low_sorted_items = sorted(
        all_items,
        key=lambda r: (_int(r["units_sold"]), _float(r["revenue"]), str(r["name"] or "").lower()),
    )

    # Rank items
    top_items = [
        {
            "rank":       idx + 1,
            "name":       r["name"],
            "units_sold": _int(r["units_sold"]),
            "revenue":    round(_float(r["revenue"]), 2),
        }
        for idx, r in enumerate(top_sorted_items[:10])
    ]

    low_items = [
        {
            "rank":       idx + 1,
            "name":       r["name"],
            "units_sold": _int(r["units_sold"]),
            "revenue":    round(_float(r["revenue"]), 2),
        }
        for idx, r in enumerate(low_sorted_items[:10])
    ]

    hourly_data = [
        {
            "hour":       _int(r["hour"]),
            "avg_orders": round(_float(r["order_cnt"]) / total_days, 2),
        }
        for r in hourly_rows
    ]

    return {
        "top_items":   top_items,
        "low_items":   low_items,
        "hourly_data": hourly_data,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/reviews?category=all
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_review_category(raw: str) -> str:
    value = (raw or "").strip().lower()
    aliases = {
        "all": "all",
        "fast food": "Fast Food",
        "fastfood": "Fast Food",
        "chinese": "Chinese",
        "bbq": "BBQ",
        "pakistani": "Desi",
        "desi": "Desi",
        "drinks": "Drinks",
        "drink": "Drinks",
    }
    return aliases.get(value, raw.strip()) if value else "all"


@router.get("/reviews")
def admin_reviews(
    category: str = Query(default="all", description="Cuisine category filter or 'all'"),
    _: Dict = Depends(_require_admin),
):
    """
        Returns all-time ratings for menu items and deals, filtered by cuisine category.

    Shape:
      categories: ["BBQ", "Chinese", "Desi", "Drinks", "Fast Food"]
            items: [{item_id, item_name, category, avg_rating, total_reviews, item_type}]
    """
    normalized_category = _normalize_review_category(category)
    params = {"category": normalized_category}

    categories_sql = text("""
        WITH deal_cuisine_votes AS (
            SELECT
                di.deal_id,
                mi.item_cuisine AS category,
                COUNT(*) AS vote_count
            FROM public.deal_item di
            JOIN public.menu_item mi ON mi.item_id = di.menu_item_id
            WHERE mi.item_cuisine IS NOT NULL
            GROUP BY di.deal_id, mi.item_cuisine
        ),
        deal_categories AS (
            SELECT deal_id, category
            FROM (
                SELECT
                    deal_id,
                    category,
                    vote_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY deal_id
                        ORDER BY vote_count DESC, category ASC
                    ) AS rn
                FROM deal_cuisine_votes
            ) ranked
            WHERE rn = 1
        )
        SELECT DISTINCT category
        FROM (
            SELECT mi.item_cuisine AS category
            FROM public.menu_item mi
            WHERE mi.item_cuisine IS NOT NULL

            UNION

            SELECT dc.category
            FROM deal_categories dc
            WHERE dc.category IS NOT NULL
        ) all_categories
        ORDER BY category ASC
    """)

    items_sql = text("""
        WITH deal_cuisine_votes AS (
            SELECT
                di.deal_id,
                mi.item_cuisine AS category,
                COUNT(*) AS vote_count
            FROM public.deal_item di
            JOIN public.menu_item mi ON mi.item_id = di.menu_item_id
            WHERE mi.item_cuisine IS NOT NULL
            GROUP BY di.deal_id, mi.item_cuisine
        ),
        deal_categories AS (
            SELECT deal_id, category
            FROM (
                SELECT
                    deal_id,
                    category,
                    vote_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY deal_id
                        ORDER BY vote_count DESC, category ASC
                    ) AS rn
                FROM deal_cuisine_votes
            ) ranked
            WHERE rn = 1
        ),
        rated_entities AS (
            SELECT
                mi.item_id,
                mi.item_name,
                mi.item_cuisine AS category,
                COALESCE(AVG(f.rating::numeric), 0) AS avg_rating,
                COUNT(f.feedback_id)                AS total_reviews,
                'menu_item'::text                   AS item_type
            FROM public.menu_item mi
            LEFT JOIN public.feedback f ON f.item_id = mi.item_id
            WHERE (:category = 'all' OR mi.item_cuisine = :category)
            GROUP BY mi.item_id, mi.item_name, mi.item_cuisine

            UNION ALL

            SELECT
                d.deal_id AS item_id,
                d.deal_name AS item_name,
                dc.category,
                COALESCE(AVG(f.rating::numeric), 0) AS avg_rating,
                COUNT(f.feedback_id)                AS total_reviews,
                'deal'::text                        AS item_type
            FROM public.deal d
            JOIN deal_categories dc ON dc.deal_id = d.deal_id
            LEFT JOIN public.feedback f ON f.deal_id = d.deal_id
            WHERE (:category = 'all' OR dc.category = :category)
            GROUP BY d.deal_id, d.deal_name, dc.category
        )
        SELECT item_id, item_name, category, avg_rating, total_reviews, item_type
        FROM rated_entities
        ORDER BY avg_rating ASC, total_reviews DESC, item_name ASC
    """)

    with SQL_ENGINE.connect() as conn:
        category_rows = conn.execute(categories_sql).mappings().all()
        item_rows = conn.execute(items_sql, params).mappings().all()

    categories = [r["category"] for r in category_rows]
    items = [
        {
            "item_id": _int(r["item_id"]),
            "item_name": r["item_name"],
            "category": r["category"],
            "avg_rating": round(_float(r["avg_rating"]), 1),
            "total_reviews": _int(r["total_reviews"]),
            "item_type": r.get("item_type", "menu_item"),
        }
        for r in item_rows
    ]

    return {
        "categories": categories,
        "items": items,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/agents
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/agents")
def admin_agents(_: Dict = Depends(_require_admin)):
    """
    Returns aggregate performance stats for the 4 AI agents in the system:
      Chatbot, Personalization, Custom Deal, and Upsell.

    Revenue/orders are attributed by tracing orders that involved each agent's
    feature (chat sessions, custom deals, upsell-triggered reorders, etc.).
    """
    with SQL_ENGINE.connect() as conn:
        # --- Total platform figures (for context) ---
        totals = conn.execute(
            text("""
                SELECT
                    COUNT(*)                      AS total_orders,
                    COALESCE(SUM(total_price), 0) AS total_revenue
                FROM orders
                WHERE status NOT IN ('cancelled')
            """)
        ).mappings().fetchone()

        # --- Chatbot agent: orders placed after a chat session ---
        chatbot = conn.execute(
            text("""
                SELECT
                    COUNT(DISTINCT o.order_id)    AS orders,
                    COALESCE(SUM(o.total_price), 0) AS revenue
                FROM orders o
                JOIN cart c ON c.cart_id = o.cart_id
                WHERE o.status NOT IN ('cancelled')
                  AND EXISTS (
                      SELECT 1
                      FROM sessions s
                      WHERE s.user_id = c.user_id
                        AND s.created_at BETWEEN o.created_at - INTERVAL '2 hours' AND o.created_at
                  )
            """)
        ).mappings().fetchone()

        # --- Personalization agent: orders containing a recommended item ---
        personalization = conn.execute(
            text("""
                SELECT
                    COUNT(DISTINCT o.order_id)      AS orders,
                    COALESCE(SUM(o.total_price), 0) AS revenue
                FROM orders o
                WHERE o.status NOT IN ('cancelled')
                  AND EXISTS (
                      SELECT 1 FROM order_items oi
                      WHERE oi.order_id = o.order_id AND oi.item_type = 'menu_item'
                  )
            """)
        ).mappings().fetchone()

        # --- Custom Deal agent: orders containing a custom deal ---
        custom_deal = conn.execute(
            text("""
                SELECT
                    COUNT(DISTINCT o.order_id)      AS orders,
                    COALESCE(SUM(o.total_price), 0) AS revenue
                FROM orders o
                WHERE o.status NOT IN ('cancelled')
                  AND EXISTS (
                      SELECT 1 FROM order_items oi
                      WHERE oi.order_id = o.order_id AND oi.item_type = 'custom_deal'
                  )
            """)
        ).mappings().fetchone()

        # --- Upsell agent: orders that contain a deal item ---
        upsell = conn.execute(
            text("""
                SELECT
                    COUNT(DISTINCT o.order_id)      AS orders,
                    COALESCE(SUM(o.total_price), 0) AS revenue
                FROM orders o
                WHERE o.status NOT IN ('cancelled')
                  AND EXISTS (
                      SELECT 1 FROM order_items oi
                      WHERE oi.order_id = o.order_id AND oi.item_type = 'deal'
                  )
            """)
        ).mappings().fetchone()

    total_orders  = _int(totals["total_orders"])
    total_revenue = round(_float(totals["total_revenue"]), 2)

    def _trend(agent_orders: int, total: int) -> float:
        """Return agent's share of total orders as a % trend."""
        return round((agent_orders / total * 100), 1) if total else 0.0

    agents: List[Dict[str, Any]] = [
        {
            "name":         "Chatbot Agent",
            "description":  "Handles natural-language ordering and menu queries",
            "orders":       _int(chatbot["orders"]),
            "revenue":      round(_float(chatbot["revenue"]), 2),
            "metric_label": "Conversation-to-order rate",
            "metric_value": f"{_trend(_int(chatbot['orders']), total_orders)} %",
            "trend_percent": _trend(_int(chatbot["orders"]), total_orders),
        },
        {
            "name":         "Personalization Agent",
            "description":  "Recommends items based on user preferences and history",
            "orders":       _int(personalization["orders"]),
            "revenue":      round(_float(personalization["revenue"]), 2),
            "metric_label": "Recommendation adoption rate",
            "metric_value": f"{_trend(_int(personalization['orders']), total_orders)} %",
            "trend_percent": _trend(_int(personalization["orders"]), total_orders),
        },
        {
            "name":         "Custom Deal Agent",
            "description":  "Creates tailored deals from natural-language requests",
            "orders":       _int(custom_deal["orders"]),
            "revenue":      round(_float(custom_deal["revenue"]), 2),
            "metric_label": "Custom deal orders",
            "metric_value": str(_int(custom_deal["orders"])),
            "trend_percent": _trend(_int(custom_deal["orders"]), total_orders),
        },
        {
            "name":         "Upsell Agent",
            "description":  "Weather-based & cross-sell deal recommendations",
            "orders":       _int(upsell["orders"]),
            "revenue":      round(_float(upsell["revenue"]), 2),
            "metric_label": "Deal orders driven",
            "metric_value": str(_int(upsell["orders"])),
            "trend_percent": _trend(_int(upsell["orders"]), total_orders),
        },
    ]

    return {
        "total_revenue": total_revenue,
        "total_orders":  total_orders,
        "agents":        agents,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/ai-suggestions
# ─────────────────────────────────────────────────────────────────────────────

class AdminAISuggestionsRequest(BaseModel):
    type: Literal["revenue", "menu", "forecast", "retention"]


_AI_SYSTEM_PROMPT = (
    "You are a professional restaurant business analyst AI for Khadim, "
    "an AI-powered restaurant in Pakistan. You are given real operational "
    "data from the restaurant. Your job is to provide specific, data-driven, "
    "actionable business recommendations. Always reference the actual numbers "
    "from the data. Be concise and direct. Never give vague advice. "
    "Return ONLY valid JSON - no markdown, no explanation outside the JSON."
)


def _extract_json_object(raw: str) -> Dict[str, Any] | None:
    if not raw:
        return None

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _normalize_suggestions(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_items = parsed.get("suggestions")
    if not isinstance(raw_items, list):
        return []

    suggestions: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        heading = str(item.get("heading", "")).strip()
        text_value = str(item.get("text", "")).strip()
        if not heading or not text_value:
            continue
        suggestions.append({
            "index": idx,
            "heading": heading,
            "text": text_value,
        })

    return suggestions[:4]


def _call_groq_with_timeout(system_prompt: str, user_prompt: str) -> str:
    if not _groq_client:
        raise RuntimeError("GROQ_API2_KEY is not configured")

    def _invoke() -> str:
        completion = _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        return completion.choices[0].message.content or ""

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_invoke)
        try:
            return future.result(timeout=10)
        except FuturesTimeoutError as exc:
            raise RuntimeError("Groq request timed out") from exc


def _build_revenue_ai_data(conn) -> Dict[str, Any]:
    current = conn.execute(
        text(
            """
            SELECT
                COALESCE(SUM(total_price), 0) AS revenue,
                COUNT(*) AS orders,
                COALESCE(AVG(total_price), 0) AS aov
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '30 days'
              AND status NOT IN ('cancelled', 'declined')
            """
        )
    ).mappings().fetchone()

    previous = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '60 days'
              AND created_at < NOW() - INTERVAL '30 days'
              AND status NOT IN ('cancelled', 'declined')
            """
        )
    ).mappings().fetchone()

    best_day = conn.execute(
        text(
            """
            SELECT
                DATE(created_at AT TIME ZONE 'Asia/Karachi') AS day,
                COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '30 days'
              AND status NOT IN ('cancelled', 'declined')
            GROUP BY DATE(created_at AT TIME ZONE 'Asia/Karachi')
            ORDER BY revenue DESC
            LIMIT 1
            """
        )
    ).mappings().fetchone()

    worst_day = conn.execute(
        text(
            """
            SELECT
                DATE(created_at AT TIME ZONE 'Asia/Karachi') AS day,
                COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '30 days'
              AND status NOT IN ('cancelled', 'declined')
            GROUP BY DATE(created_at AT TIME ZONE 'Asia/Karachi')
            ORDER BY revenue ASC
            LIMIT 1
            """
        )
    ).mappings().fetchone()

    category_rows = conn.execute(
        text(
            """
            SELECT
                CASE
                    WHEN oi.item_type = 'deal' THEN 'Deals'
                    WHEN oi.item_type = 'custom_deal' THEN 'Custom Deals'
                    ELSE COALESCE(mi.item_category, 'Other')
                END AS category,
                COALESCE(SUM(oi.quantity * oi.unit_price_snapshot), 0) AS revenue
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id
            LEFT JOIN menu_item mi ON mi.item_id = oi.item_id AND oi.item_type = 'menu_item'
            WHERE o.created_at >= NOW() - INTERVAL '30 days'
              AND o.status NOT IN ('cancelled', 'declined')
            GROUP BY category
            ORDER BY revenue DESC
            LIMIT 3
            """
        )
    ).mappings().fetchall()

    current_revenue = _float(current["revenue"])
    previous_revenue = _float(previous["revenue"])
    change_pct = ((current_revenue - previous_revenue) / previous_revenue * 100.0) if previous_revenue > 0 else 0.0

    return {
        "total_revenue_last_30_days": round(current_revenue, 2),
        "total_revenue_previous_30_days": round(previous_revenue, 2),
        "revenue_change_percent": round(change_pct, 2),
        "average_order_value_last_30_days": round(_float(current["aov"]), 2),
        "total_orders_last_30_days": _int(current["orders"]),
        "best_revenue_day": {
            "date": best_day["day"].isoformat() if best_day and best_day["day"] else None,
            "amount": round(_float(best_day["revenue"]), 2) if best_day else 0.0,
        },
        "worst_revenue_day": {
            "date": worst_day["day"].isoformat() if worst_day and worst_day["day"] else None,
            "amount": round(_float(worst_day["revenue"]), 2) if worst_day else 0.0,
        },
        "top_categories_by_revenue": [
            {"category": r["category"], "revenue": round(_float(r["revenue"]), 2)}
            for r in category_rows
        ],
    }


def _build_menu_ai_data(conn) -> Dict[str, Any]:
    rows = conn.execute(
        text(
            """
            WITH sales AS (
                SELECT
                    mi.item_id,
                    mi.item_name,
                    COALESCE(SUM(oi.quantity), 0) AS units_sold,
                    COALESCE(SUM(oi.quantity * oi.unit_price_snapshot), 0) AS revenue
                FROM menu_item mi
                LEFT JOIN order_items oi
                       ON oi.item_id = mi.item_id
                      AND oi.item_type = 'menu_item'
                LEFT JOIN orders o
                       ON o.order_id = oi.order_id
                      AND o.status NOT IN ('cancelled', 'declined')
                GROUP BY mi.item_id, mi.item_name
            ),
            ratings AS (
                SELECT
                    f.item_id,
                    ROUND(AVG(f.rating)::numeric, 2) AS avg_rating,
                    COUNT(*) AS review_count
                FROM feedback f
                WHERE f.item_id IS NOT NULL
                GROUP BY f.item_id
            )
            SELECT
                s.item_name,
                s.units_sold,
                s.revenue,
                COALESCE(r.avg_rating, 0) AS avg_rating,
                COALESCE(r.review_count, 0) AS review_count
            FROM sales s
            LEFT JOIN ratings r ON r.item_id = s.item_id
            """
        )
    ).mappings().fetchall()

    sorted_desc = sorted(rows, key=lambda r: _int(r["units_sold"]), reverse=True)
    sorted_asc = sorted(rows, key=lambda r: _int(r["units_sold"]))

    def _project(source_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "name": r["item_name"],
                "units": _int(r["units_sold"]),
                "revenue": round(_float(r["revenue"]), 2),
                "avg_rating": round(_float(r["avg_rating"]), 2),
            }
            for r in source_rows
        ]

    low_rated = [
        {
            "name": r["item_name"],
            "rating": round(_float(r["avg_rating"]), 2),
            "review_count": _int(r["review_count"]),
        }
        for r in rows
        if _int(r["review_count"]) > 0 and _float(r["avg_rating"]) < 3.0
    ]
    low_rated = sorted(low_rated, key=lambda r: r["rating"])[:10]

    most_reviewed = None
    if rows:
        by_reviews = sorted(rows, key=lambda r: _int(r["review_count"]), reverse=True)
        if _int(by_reviews[0]["review_count"]) > 0:
            most_reviewed = {
                "name": by_reviews[0]["item_name"],
                "avg_rating": round(_float(by_reviews[0]["avg_rating"]), 2),
                "review_count": _int(by_reviews[0]["review_count"]),
            }

    return {
        "top_5_items_by_units": _project(sorted_desc[:5]),
        "bottom_5_items_by_units": _project(sorted_asc[:5]),
        "items_with_avg_rating_below_3": low_rated,
        "most_reviewed_item": most_reviewed,
    }


def _build_forecast_ai_data(conn) -> Dict[str, Any]:
    dow_rows = conn.execute(
        text(
            """
            WITH daily AS (
                SELECT
                    DATE(o.created_at AT TIME ZONE 'Asia/Karachi') AS day,
                    EXTRACT(ISODOW FROM o.created_at AT TIME ZONE 'Asia/Karachi')::int AS dow,
                    COUNT(*) AS orders_count
                FROM orders o
                WHERE o.status NOT IN ('cancelled', 'declined')
                GROUP BY day, dow
            )
            SELECT dow, ROUND(AVG(orders_count)::numeric, 2) AS avg_orders
            FROM daily
            GROUP BY dow
            ORDER BY dow
            """
        )
    ).mappings().fetchall()

    hourly_rows = conn.execute(
        text(
            """
            WITH hour_daily AS (
                SELECT
                    DATE(o.created_at AT TIME ZONE 'Asia/Karachi') AS day,
                    EXTRACT(HOUR FROM o.created_at AT TIME ZONE 'Asia/Karachi')::int AS hour,
                    COUNT(*) AS orders_count
                FROM orders o
                WHERE o.status NOT IN ('cancelled', 'declined')
                GROUP BY day, hour
            )
            SELECT hour, ROUND(AVG(orders_count)::numeric, 2) AS avg_orders
            FROM hour_daily
            GROUP BY hour
            ORDER BY hour
            """
        )
    ).mappings().fetchall()

    top_items_rows = conn.execute(
        text(
            """
            SELECT
                oi.name_snapshot AS item_name,
                COALESCE(SUM(oi.quantity), 0) AS units
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id
            WHERE o.created_at >= NOW() - INTERVAL '7 days'
              AND o.status NOT IN ('cancelled', 'declined')
            GROUP BY oi.name_snapshot
            ORDER BY units DESC
            LIMIT 3
            """
        )
    ).mappings().fetchall()

    last_7_days_rows = conn.execute(
        text(
            """
            WITH days AS (
                SELECT generate_series(
                    CURRENT_DATE - INTERVAL '6 days',
                    CURRENT_DATE,
                    INTERVAL '1 day'
                )::date AS day
            )
            SELECT
                d.day,
                COALESCE(COUNT(o.order_id), 0) AS orders_count
            FROM days d
            LEFT JOIN orders o
                   ON DATE(o.created_at AT TIME ZONE 'Asia/Karachi') = d.day
                  AND o.status NOT IN ('cancelled', 'declined')
            GROUP BY d.day
            ORDER BY d.day
            """
        )
    ).mappings().fetchall()

    dow_name = {
        1: "Monday",
        2: "Tuesday",
        3: "Wednesday",
        4: "Thursday",
        5: "Friday",
        6: "Saturday",
        7: "Sunday",
    }

    avg_orders_per_day = {dow_name[i]: 0.0 for i in range(1, 8)}
    for row in dow_rows:
        avg_orders_per_day[dow_name[_int(row["dow"])]] = round(_float(row["avg_orders"]), 2)

    avg_orders_per_hour = {str(i): 0.0 for i in range(24)}
    for row in hourly_rows:
        avg_orders_per_hour[str(_int(row["hour"]))] = round(_float(row["avg_orders"]), 2)

    return {
        "average_orders_per_day_of_week": avg_orders_per_day,
        "average_orders_per_hour": avg_orders_per_hour,
        "top_3_items_by_order_volume_last_7_days": [
            {"name": row["item_name"], "units": _int(row["units"])} for row in top_items_rows
        ],
        "last_7_days_order_counts_by_day": [
            {"date": row["day"].isoformat(), "orders": _int(row["orders_count"])}
            for row in last_7_days_rows
        ],
    }


def _build_retention_ai_data(conn) -> Dict[str, Any]:
    user_activity = conn.execute(
        text(
            """
            WITH user_last_order AS (
                SELECT
                    c.user_id,
                    MAX(o.created_at) AS last_order_at
                FROM orders o
                JOIN cart c ON c.cart_id = o.cart_id
                WHERE o.status NOT IN ('cancelled', 'declined')
                GROUP BY c.user_id
            )
            SELECT
                COUNT(*) FILTER (WHERE last_order_at >= NOW() - INTERVAL '30 days') AS active_users,
                COUNT(*) FILTER (WHERE last_order_at < NOW() - INTERVAL '30 days') AS inactive_users
            FROM user_last_order
            """
        )
    ).mappings().fetchone()

    top_customers_rows = conn.execute(
        text(
            """
            SELECT
                c.user_id,
                COALESCE(u.full_name, 'Unknown') AS customer_name,
                COUNT(*) AS total_orders,
                COALESCE(SUM(o.total_price), 0) AS total_spend,
                MAX(o.created_at) AS last_order_at
            FROM orders o
            JOIN cart c ON c.cart_id = o.cart_id
            LEFT JOIN auth.app_users u ON u.user_id = c.user_id
            WHERE o.status NOT IN ('cancelled', 'declined')
            GROUP BY c.user_id, COALESCE(u.full_name, 'Unknown')
            ORDER BY total_orders DESC, total_spend DESC
            LIMIT 5
            """
        )
    ).mappings().fetchall()

    inactive_former_customers_rows = conn.execute(
        text(
            """
            WITH user_stats AS (
                SELECT
                    c.user_id,
                    COALESCE(u.full_name, 'Unknown') AS customer_name,
                    COUNT(*) AS total_orders,
                    COALESCE(SUM(o.total_price), 0) AS total_spend,
                    MAX(o.created_at) AS last_order_at
                FROM orders o
                JOIN cart c ON c.cart_id = o.cart_id
                LEFT JOIN auth.app_users u ON u.user_id = c.user_id
                WHERE o.status NOT IN ('cancelled', 'declined')
                GROUP BY c.user_id, COALESCE(u.full_name, 'Unknown')
            )
            SELECT
                user_id,
                customer_name,
                total_orders,
                total_spend,
                last_order_at,
                EXTRACT(DAY FROM (NOW() - last_order_at))::int AS days_since_last_order
            FROM user_stats
            WHERE last_order_at < NOW() - INTERVAL '30 days'
              AND total_orders >= 3
            ORDER BY total_orders DESC, last_order_at ASC
            LIMIT 5
            """
        )
    ).mappings().fetchall()

    low_rated_rows = conn.execute(
        text(
            """
            SELECT
                mi.item_name,
                ROUND(AVG(f.rating)::numeric, 2) AS avg_rating
            FROM feedback f
            JOIN menu_item mi ON mi.item_id = f.item_id
            WHERE f.item_id IS NOT NULL
            GROUP BY mi.item_name
            ORDER BY avg_rating ASC
            LIMIT 3
            """
        )
    ).mappings().fetchall()

    avg_gap = conn.execute(
        text(
            """
            WITH ordered AS (
                SELECT
                    c.user_id,
                    o.created_at,
                    LAG(o.created_at) OVER (PARTITION BY c.user_id ORDER BY o.created_at) AS prev_order_at
                FROM orders o
                JOIN cart c ON c.cart_id = o.cart_id
                WHERE o.status NOT IN ('cancelled', 'declined')
            )
            SELECT
                COALESCE(AVG(EXTRACT(EPOCH FROM (created_at - prev_order_at)) / 86400.0), 0) AS avg_days_between_orders
            FROM ordered
            WHERE prev_order_at IS NOT NULL
            """
        )
    ).mappings().fetchone()

    return {
        "active_users_last_30_days": _int(user_activity["active_users"]),
        "users_not_ordered_last_30_days_but_ordered_before": _int(user_activity["inactive_users"]),
        "top_customers_by_order_frequency": [
            {
                "user_id": _int(row["user_id"]),
                "customer_name": row["customer_name"],
                "total_orders": _int(row["total_orders"]),
                "total_spend": round(_float(row["total_spend"]), 2),
                "last_order_at": row["last_order_at"].isoformat() if row["last_order_at"] else None,
            }
            for row in top_customers_rows
        ],
        "inactive_former_frequent_customers": [
            {
                "user_id": _int(row["user_id"]),
                "customer_name": row["customer_name"],
                "total_orders": _int(row["total_orders"]),
                "total_spend": round(_float(row["total_spend"]), 2),
                "last_order_at": row["last_order_at"].isoformat() if row["last_order_at"] else None,
                "days_since_last_order": _int(row["days_since_last_order"]),
            }
            for row in inactive_former_customers_rows
        ],
        "items_with_lowest_avg_ratings": [
            {"name": row["item_name"], "rating": round(_float(row["avg_rating"]), 2)}
            for row in low_rated_rows
        ],
        "average_days_between_orders_per_user": round(_float(avg_gap["avg_days_between_orders"]), 2),
    }


def _build_user_prompt(suggestion_type: str, data_payload: Dict[str, Any]) -> str:
    payload_json = json.dumps(data_payload, ensure_ascii=True)
    format_hint = (
        "Return exactly this JSON structure: "
        '{"suggestions":[{"index":1,"heading":"short heading max 8 words",'
        '"text":"detailed recommendation with specific numbers, 2-3 sentences"}]}'
    )

    if suggestion_type == "revenue":
        return (
            "Here is the revenue data for this restaurant for the last 30 days:\n"
            f"{payload_json}\n"
            "Give 4 specific actionable recommendations to improve revenue.\n"
            "Focus on pricing, peak days, underperforming periods, and category mix.\n"
            f"{format_hint}"
        )

    if suggestion_type == "menu":
        return (
            "Here is the menu performance data for this restaurant:\n"
            f"{payload_json}\n"
            "Give 4 specific recommendations. Consider which items to promote, "
            "which to remove or improve, bundling opportunities, and quality issues.\n"
            f"{format_hint}"
        )

    if suggestion_type == "forecast":
        current_day_of_week = datetime.now(timezone.utc).astimezone().strftime("%A")
        return (
            "Here is historical order pattern data for this restaurant:\n"
            f"{payload_json}\n"
            f"Today is {current_day_of_week}. Give 4 specific recommendations "
            "about what to prepare for the next 48 hours. Include expected peak "
            "hours, which items to stock up on, staffing suggestions, "
            "and any demand patterns worth noting.\n"
            f"{format_hint}"
        )

    return (
        "Here is customer retention data for this restaurant:\n"
        f"{payload_json}\n"
        "Give 4 specific recommendations focused on two segments: "
        "(1) customers who order the most, and "
        "(2) customers who used to order frequently but are now inactive. "
        "Include loyalty/VIP tactics for top customers and win-back tactics "
        "for inactive customers, while also considering quality issues and repeat-order patterns.\n"
        f"{format_hint}"
    )


def _generate_ai_suggestions(suggestion_type: str, data_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    user_prompt = _build_user_prompt(suggestion_type, data_payload)

    first_raw = _call_groq_with_timeout(_AI_SYSTEM_PROMPT, user_prompt)
    first_json = _extract_json_object(first_raw)
    first_suggestions = _normalize_suggestions(first_json or {})
    if first_suggestions:
        return first_suggestions

    retry_prompt = (
        user_prompt
        + "\nIMPORTANT: Previous response was malformed. Return ONLY valid JSON in the exact requested structure."
    )
    retry_raw = _call_groq_with_timeout(_AI_SYSTEM_PROMPT, retry_prompt)
    retry_json = _extract_json_object(retry_raw)
    retry_suggestions = _normalize_suggestions(retry_json or {})
    if retry_suggestions:
        return retry_suggestions

    raise ValueError("Malformed JSON")


@router.post("/ai-suggestions")
def admin_ai_suggestions(payload: AdminAISuggestionsRequest, _: Dict = Depends(_require_admin)):
    if not _groq_client:
        return JSONResponse(
            status_code=500,
            content={"error": "AI service temporarily unavailable"},
        )

    try:
        with SQL_ENGINE.connect() as conn:
            if payload.type == "revenue":
                data_payload = _build_revenue_ai_data(conn)
            elif payload.type == "menu":
                data_payload = _build_menu_ai_data(conn)
            elif payload.type == "forecast":
                data_payload = _build_forecast_ai_data(conn)
            else:
                data_payload = _build_retention_ai_data(conn)

        suggestions = _generate_ai_suggestions(payload.type, data_payload)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "AI service temporarily unavailable"},
        )

    return {
        "type": payload.type,
        "suggestions": suggestions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
