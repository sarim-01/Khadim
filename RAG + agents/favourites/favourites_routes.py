from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text

from infrastructure.db import SQL_ENGINE
from auth.auth_routes import get_current_user
from infrastructure.database_connection import DatabaseConnection
from personalization.score_builder import ScoreBuilder

_executor = ThreadPoolExecutor(max_workers=2)


def _rebuild_profile(user_id: str) -> None:
    """Invalidate recommendation cache and rebuild the user profile.
    Intended to run in a background thread — never blocks the API response."""
    try:
        db_conn = DatabaseConnection.get_instance().get_connection()
        sb = ScoreBuilder(db_conn)
        sb.invalidate_cache(user_id)
        sb.build_user_profile(user_id)
    except Exception:
        pass  # Don't let personalization errors surface to the caller

router = APIRouter(prefix="/favourites", tags=["favourites"])


# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────

class ToggleFavouriteRequest(BaseModel):
    item_id: Optional[int] = None
    deal_id: Optional[int] = None
    custom_deal_id: Optional[int] = None


# ─────────────────────────────────────────────
# POST /favourites/toggle
# ─────────────────────────────────────────────

@router.post("/toggle")
def toggle_favourite(
    payload: ToggleFavouriteRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])

    # Validate exactly one type
    non_null = sum([
        payload.item_id is not None,
        payload.deal_id is not None,
        payload.custom_deal_id is not None,
    ])
    if non_null != 1:
        raise HTTPException(
            status_code=400,
            detail="Exactly one of item_id, deal_id, or custom_deal_id must be provided.",
        )

    with SQL_ENGINE.begin() as conn:
        # Build WHERE clause based on which field is set
        if payload.item_id is not None:
            where = "user_id = :uid AND item_id = :val"
            params: Dict[str, Any] = {"uid": user_id, "val": payload.item_id}
            insert_col = "item_id"
        elif payload.deal_id is not None:
            where = "user_id = :uid AND deal_id = :val"
            params = {"uid": user_id, "val": payload.deal_id}
            insert_col = "deal_id"
        else:
            where = "user_id = :uid AND custom_deal_id = :val"
            params = {"uid": user_id, "val": payload.custom_deal_id}
            insert_col = "custom_deal_id"

        # Check if exists
        existing = conn.execute(
            text(f"SELECT favourite_id FROM public.favourites WHERE {where}"),
            params,
        ).mappings().fetchone()

        if existing:
            conn.execute(
                text(f"DELETE FROM public.favourites WHERE {where}"),
                params,
            )
            action_result = {"action": "removed", "favourite_id": None}
        else:
            row = conn.execute(
                text(
                    f"INSERT INTO public.favourites (user_id, {insert_col}) "
                    f"VALUES (:uid, :val) RETURNING favourite_id"
                ),
                params,
            ).mappings().fetchone()
            action_result = {"action": "added", "favourite_id": int(row["favourite_id"])}

    # Fire-and-forget: invalidate cache + rebuild personalization profile
    _executor.submit(_rebuild_profile, user_id)

    return action_result


# ─────────────────────────────────────────────
# GET /favourites
# ─────────────────────────────────────────────

@router.get("")
def get_favourites(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = str(current_user["user_id"])

    with SQL_ENGINE.connect() as conn:
        # Menu items
        item_rows = conn.execute(
            text("""
                SELECT f.favourite_id, f.created_at,
                       m.item_id, m.item_name, m.item_price AS price, m.image_url
                FROM public.favourites f
                JOIN public.menu_item m ON m.item_id = f.item_id
                WHERE f.user_id = :uid AND f.item_id IS NOT NULL
                ORDER BY f.created_at DESC
            """),
            {"uid": user_id},
        ).mappings().all()

        # Deals
        deal_rows = conn.execute(
            text("""
                SELECT f.favourite_id, f.created_at,
                       d.deal_id, d.deal_name, d.deal_price AS price, d.image_url
                FROM public.favourites f
                JOIN public.deal d ON d.deal_id = f.deal_id
                WHERE f.user_id = :uid AND f.deal_id IS NOT NULL
                ORDER BY f.created_at DESC
            """),
            {"uid": user_id},
        ).mappings().all()

        # Custom deals (headers)
        cd_rows = conn.execute(
            text("""
                SELECT f.favourite_id, f.created_at,
                       cd.custom_deal_id, cd.total_price, cd.discount_amount, cd.group_size
                FROM public.favourites f
                JOIN public.custom_deals cd ON cd.custom_deal_id = f.custom_deal_id
                WHERE f.user_id = :uid AND f.custom_deal_id IS NOT NULL
                ORDER BY f.created_at DESC
            """),
            {"uid": user_id},
        ).mappings().all()

        # Custom deal items per deal
        custom_deals_result: List[Dict[str, Any]] = []
        for cd in cd_rows:
            cd_items = conn.execute(
                text("""
                    SELECT cdi.item_id, m.item_name, cdi.quantity, cdi.unit_price
                    FROM public.custom_deal_items cdi
                    JOIN public.menu_item m ON m.item_id = cdi.item_id
                    WHERE cdi.custom_deal_id = :cdid
                    ORDER BY cdi.item_id
                """),
                {"cdid": cd["custom_deal_id"]},
            ).mappings().all()

            custom_deals_result.append({
                "favourite_id": int(cd["favourite_id"]),
                "custom_deal_id": int(cd["custom_deal_id"]),
                "total_price": float(cd["total_price"] or 0),
                "discount_amount": float(cd["discount_amount"] or 0),
                "group_size": int(cd["group_size"] or 1),
                "created_at": cd["created_at"].isoformat() if cd["created_at"] else None,
                "items": [
                    {
                        "item_id": int(r["item_id"]),
                        "item_name": r["item_name"],
                        "quantity": int(r["quantity"] or 1),
                        "unit_price": float(r["unit_price"] or 0),
                    }
                    for r in cd_items
                ],
            })

    return {
        "items": [
            {
                "favourite_id": int(r["favourite_id"]),
                "item_id": int(r["item_id"]),
                "item_name": r["item_name"],
                "price": float(r["price"] or 0),
                "image_url": r["image_url"] or "",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in item_rows
        ],
        "deals": [
            {
                "favourite_id": int(r["favourite_id"]),
                "deal_id": int(r["deal_id"]),
                "deal_name": r["deal_name"],
                "price": float(r["price"] or 0),
                "image_url": r["image_url"] or "",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in deal_rows
        ],
        "custom_deals": custom_deals_result,
    }


# ─────────────────────────────────────────────
# GET /favourites/status
# ─────────────────────────────────────────────

@router.get("/status")
def get_favourite_status(
    item_id: Optional[int] = None,
    deal_id: Optional[int] = None,
    custom_deal_id: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])

    if item_id is not None:
        where = "user_id = :uid AND item_id = :val"
        params: Dict[str, Any] = {"uid": user_id, "val": item_id}
    elif deal_id is not None:
        where = "user_id = :uid AND deal_id = :val"
        params = {"uid": user_id, "val": deal_id}
    elif custom_deal_id is not None:
        where = "user_id = :uid AND custom_deal_id = :val"
        params = {"uid": user_id, "val": custom_deal_id}
    else:
        return {"is_favourite": False, "favourite_id": None}

    with SQL_ENGINE.connect() as conn:
        row = conn.execute(
            text(f"SELECT favourite_id FROM public.favourites WHERE {where}"),
            params,
        ).mappings().fetchone()

    if row:
        return {"is_favourite": True, "favourite_id": int(row["favourite_id"])}
    return {"is_favourite": False, "favourite_id": None}
