from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def _clean(value: Optional[str]) -> Optional[str]:
    """Trim whitespace and return None for empty values."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _table_exists(db: Session, *, table_name: str) -> bool:
    """Best-effort table existence check (safe across migrations/environments)."""
    try:
        v = db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :t
                LIMIT 1
                """
            ),
            {"t": table_name},
        ).scalar()
        return bool(v)
    except Exception:
        return False


def resolve_marketplace_for_sold_item(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    explicit_marketplace: Optional[str] = None,
) -> str:
    """Resolve marketplace/platform for a sold item.

    Resolution priority:
      1) explicit marketplace from payload
      2) listing platform if available
      3) item/listing metadata if available
      4) business_settings.main_marketplace
      5) "Unknown"

    Returns a clean string (never None). Production-safe: missing tables/rows
    fall through to the next option.
    """

    # 1) Explicit from payload
    explicit = _clean(explicit_marketplace)
    if explicit:
        return explicit

    # 2) listing platform if available (sales -> listings)
    try:
        if _table_exists(db, table_name="sales") and _table_exists(
            db, table_name="listings"
        ):
            platform = db.execute(
                text(
                    """
                    SELECT l.platform
                    FROM sales s
                    JOIN listings l
                      ON l.listing_id = s.listing_id
                    WHERE s.business_id = :business_id
                      AND s.item_id = :item_id
                    ORDER BY s.created_at DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"business_id": business_id, "item_id": item_id},
            ).scalar()
            platform_clean = _clean(platform)
            if platform_clean:
                return platform_clean
    except Exception:
        pass

    # 3) item/listing metadata if available (item_events.details)
    try:
        if _table_exists(db, table_name="item_events"):
            mp = db.execute(
                text(
                    """
                    SELECT
                      COALESCE(
                        NULLIF(BTRIM(details->>'marketplace'), ''),
                        NULLIF(BTRIM(details->>'platform'), '')
                      ) AS mp
                    FROM item_events
                    WHERE business_id = :business_id
                      AND item_id = :item_id
                      AND details IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"business_id": business_id, "item_id": item_id},
            ).scalar()
            mp_clean = _clean(mp)
            if mp_clean:
                return mp_clean
    except Exception:
        pass

    # 4) business_settings.main_marketplace
    try:
        if _table_exists(db, table_name="business_settings"):
            main = db.execute(
                text(
                    """
                    SELECT main_marketplace
                    FROM business_settings
                    WHERE business_id = :business_id
                    LIMIT 1
                    """
                ),
                {"business_id": business_id},
            ).scalar()
            main_clean = _clean(main)
            if main_clean:
                return main_clean
    except Exception:
        pass

    # 5) Final fallback
    return "Unknown"
