from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import text


def _rows_as_dicts(result: Any) -> List[Dict[str, Any]]:
    try:
        return [dict(r) for r in result.mappings().all()]
    except Exception:
        keys = list(result.keys())
        rows = result.fetchall()
        return [dict(zip(keys, row)) for row in rows]


def _first_row_as_dict(result: Any) -> Dict[str, Any]:
    try:
        row = result.mappings().first()
        return dict(row) if row else {}
    except Exception:
        keys = list(result.keys())
        row = result.fetchone()
        return dict(zip(keys, row)) if row else {}


def _execute(db: Any, sql_text: str, params: Dict[str, Any]) -> Any:
    return db.execute(text(sql_text), params)


def get_items_columns(db: Any) -> List[str]:
    res = _execute(
        db,
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'items';
        """,
        {},
    )
    rows = _rows_as_dicts(res)
    return [r["column_name"] for r in rows if "column_name" in r]


# ---------------------------------------------------------------------------
# Fetch one item (scoped) with enterprise Deleted visibility control
# ---------------------------------------------------------------------------

def fetch_one_item_scoped(
    db: Any,
    *,
    business_id: str,
    item_id: str,
    include_deleted: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Fetch a single item by business_id + item_id.

    Contract:
    - include_deleted=False (default): hides Deleted items (returns None)
    - include_deleted=True: returns Deleted items as well

    NOTE: Service layer owns the API behavior; this flag simply allows the
    service to implement "404 unless include_deleted=true" deterministically.
    """
    where_deleted = "" if include_deleted else " AND status <> 'Deleted'"

    res = _execute(
        db,
        f"""
        SELECT *
        FROM items
        WHERE business_id = :business_id
          AND item_id = :item_id
          {where_deleted}
        LIMIT 1;
        """,
        {"business_id": business_id, "item_id": item_id},
    )
    row = _first_row_as_dict(res)
    return row or None


def insert_item_event_scoped(
    db: Any,
    *,
    business_id: str,
    item_id: str,
    event_type: str,
    details_json: Optional[Dict[str, Any]] = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO item_events
                (event_id, business_id, item_id, event_type, details)
            VALUES
                (:event_id, :business_id, :item_id, :event_type, CAST(:details AS jsonb))
            """
        ),
        {
            "event_id": str(uuid.uuid4()),
            "business_id": business_id,
            "item_id": item_id,
            "event_type": event_type,
            "details": json.dumps(details_json) if details_json is not None else None,
        },
    )


# ---------------------------------------------------------------------------
# Soft delete / restore (enterprise attribution)
# ---------------------------------------------------------------------------

def soft_delete_item_scoped(
    db: Any,
    *,
    business_id: str,
    item_id: str,
    deleted_by: Optional[str] = None,
) -> int:
    """
    Soft delete: status='Deleted', sets deleted_at, status_updated_at, and deleted_by.
    Returns affected rowcount (0 or 1).
    """
    res = _execute(
        db,
        """
        UPDATE items
        SET status = 'Deleted',
            deleted_at = NOW(),
            status_updated_at = NOW(),
            deleted_by = CAST(:deleted_by AS uuid)
        WHERE business_id = :business_id
          AND item_id = :item_id
          AND status <> 'Deleted';
        """,
        {
            "business_id": business_id,
            "item_id": item_id,
            "deleted_by": deleted_by,
        },
    )
    try:
        return int(res.rowcount or 0)
    except Exception:
        return 0


def restore_item_scoped(
    db: Any,
    *,
    business_id: str,
    item_id: str,
    restored_by: Optional[str] = None,
) -> int:
    """
    Restore: status='Archived', clears deleted_at and deleted_by, sets restored_by, updates status_updated_at.
    Returns affected rowcount (0 or 1).
    """
    res = _execute(
        db,
        """
        UPDATE items
        SET status = 'Archived',
            deleted_at = NULL,
            deleted_by = NULL,
            restored_by = CAST(:restored_by AS uuid),
            status_updated_at = NOW()
        WHERE business_id = :business_id
          AND item_id = :item_id
          AND status = 'Deleted';
        """,
        {
            "business_id": business_id,
            "item_id": item_id,
            "restored_by": restored_by,
        },
    )
    try:
        return int(res.rowcount or 0)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Stats (enterprise Deleted visibility alignment)
# ---------------------------------------------------------------------------

def fetch_items_stats(
    db: Any,
    *,
    business_id: str,
    status: Optional[str] = None,
    safe_to_sell: Optional[bool] = None,
    include_deleted: bool = False,
) -> Dict[str, Any]:
    """
    Enterprise stats contract:
    - By default (include_deleted=False), Deleted items are excluded.
    - include_deleted=True includes Deleted items in aggregates.
    - If status='Deleted' is requested, caller should set include_deleted=True.
      (Service enforces; repo also aligns.)
    """
    where_clauses = ["business_id = :business_id"]
    params: Dict[str, Any] = {"business_id": business_id}

    if not include_deleted:
        where_clauses.append("status <> 'Deleted'")

    if status is not None and str(status).strip() != "":
        where_clauses.append("status = :status")
        params["status"] = status

    if safe_to_sell is not None:
        where_clauses.append("safe_to_sell = :safe_to_sell")
        params["safe_to_sell"] = safe_to_sell

    where_sql = " AND ".join(where_clauses)

    totals_sql = f"""
        SELECT
            COUNT(*)::int AS total_items,

            COALESCE(SUM(estimated_profit), 0)::float AS sum_estimated_profit,
            COALESCE(AVG(estimated_profit), 0)::float AS avg_estimated_profit,

            COALESCE(AVG(total_fee_percent), 0)::float AS avg_total_fee_percent,
            COALESCE(AVG(multiplier), 0)::float AS avg_multiplier,
            COALESCE(AVG(suggested_price), 0)::float AS avg_suggested_price,
            COALESCE(AVG(min_price), 0)::float AS avg_min_price
        FROM items
        WHERE {where_sql};
    """

    by_status_sql = f"""
        SELECT status, COUNT(*)::int AS cnt
        FROM items
        WHERE {where_sql}
        GROUP BY status;
    """

    by_safe_sql = f"""
        SELECT safe_to_sell, COUNT(*)::int AS cnt
        FROM items
        WHERE {where_sql}
        GROUP BY safe_to_sell;
    """

    reasons_sql = f"""
        SELECT
            reason_code,
            COUNT(*)::int AS cnt
        FROM (
            SELECT
                CASE
                    WHEN jsonb_typeof(elem) = 'string' THEN trim(both '"' from elem::text)
                    WHEN jsonb_typeof(elem) = 'object' THEN COALESCE(elem->>'code', 'UNKNOWN')
                    ELSE 'UNKNOWN'
                END AS reason_code
            FROM items i
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN i.safe_to_sell_reasons IS NULL THEN '[]'::jsonb
                    WHEN jsonb_typeof(i.safe_to_sell_reasons) = 'array' THEN i.safe_to_sell_reasons
                    WHEN jsonb_typeof(i.safe_to_sell_reasons) = 'object' THEN COALESCE(i.safe_to_sell_reasons->'reasons', '[]'::jsonb)
                    ELSE '[]'::jsonb
                END
            ) AS elem
            WHERE {where_sql}
        ) t
        WHERE reason_code IS NOT NULL AND reason_code <> ''
        GROUP BY reason_code
        ORDER BY cnt DESC;
    """

    totals_row = _first_row_as_dict(_execute(db, totals_sql, params))
    by_status_rows = _rows_as_dicts(_execute(db, by_status_sql, params))
    by_safe_rows = _rows_as_dicts(_execute(db, by_safe_sql, params))

    reasons: Dict[str, int] = {}
    try:
        reasons_rows = _rows_as_dicts(_execute(db, reasons_sql, params))
        for r in reasons_rows:
            reasons[str(r.get("reason_code"))] = int(r.get("cnt") or 0)
    except Exception:
        reasons = {}

    by_status: Dict[str, int] = {}
    for r in by_status_rows:
        if r.get("status") is None:
            continue
        by_status[str(r["status"])] = int(r.get("cnt") or 0)

    safe_counts: Dict[str, int] = {}
    for r in by_safe_rows:
        key = "true" if r.get("safe_to_sell") is True else "false"
        safe_counts[key] = int(r.get("cnt") or 0)

    return {
        "total_items": int(totals_row.get("total_items") or 0),
        "by_status": by_status,
        "safe_to_sell": safe_counts,
        "profit": {
            "sum_estimated_profit": float(totals_row.get("sum_estimated_profit") or 0.0),
            "avg_estimated_profit": float(totals_row.get("avg_estimated_profit") or 0.0),
        },
        "pricing": {
            "avg_total_fee_percent": float(totals_row.get("avg_total_fee_percent") or 0.0),
            "avg_multiplier": float(totals_row.get("avg_multiplier") or 0.0),
            "avg_suggested_price": float(totals_row.get("avg_suggested_price") or 0.0),
            "avg_min_price": float(totals_row.get("avg_min_price") or 0.0),
        },
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Inventory intelligence
# ---------------------------------------------------------------------------

def fetch_inventory_status_summary(
    db: Any,
    *,
    business_id: str,
    include_deleted: bool = False,
) -> Dict[str, Any]:
    where_parts = ["business_id = :business_id"]
    params: Dict[str, Any] = {"business_id": business_id}

    if not include_deleted:
        where_parts.append("status <> 'Deleted'")

    where_sql = " AND ".join(where_parts)

    totals_sql = f"""
        SELECT COUNT(*)::int AS total_items
        FROM items
        WHERE {where_sql};
    """

    by_status_sql = f"""
        SELECT
            COALESCE(status, 'Unknown') AS status,
            COUNT(*)::int AS cnt
        FROM items
        WHERE {where_sql}
        GROUP BY COALESCE(status, 'Unknown')
        ORDER BY COALESCE(status, 'Unknown');
    """

    totals_row = _first_row_as_dict(_execute(db, totals_sql, params))
    status_rows = _rows_as_dicts(_execute(db, by_status_sql, params))

    by_status: Dict[str, int] = {}
    for r in status_rows:
        by_status[str(r.get("status") or "Unknown")] = int(r.get("cnt") or 0)

    return {
        "total_items": int(totals_row.get("total_items") or 0),
        "by_status": by_status,
    }


def fetch_inventory_aging_rows(
    db: Any,
    *,
    business_id: str,
    include_deleted: bool = False,
    only_active: bool = False,
    min_age_days: Optional[int] = None,
    limit: int,
    offset: int,
) -> List[Dict[str, Any]]:
    """
    Schema-safe inventory aging query.

    IMPORTANT:
    We use to_jsonb(i)->>'field' for optional metadata fields like sku/brand/size
    so the query does not fail if those physical columns do not exist in this DB.
    """
    where_parts = ["i.business_id = :business_id"]
    params: Dict[str, Any] = {
        "business_id": business_id,
        "limit": int(limit),
        "offset": int(offset),
    }

    if not include_deleted:
        where_parts.append("i.status <> 'Deleted'")

    if only_active:
        where_parts.append("i.status = 'Active'")

    if min_age_days is not None:
        params["min_age_days"] = int(min_age_days)
        where_parts.append(
            """
            DATE_PART(
                'day',
                NOW() - COALESCE(i.active_at, i.created_at)
            ) >= :min_age_days
            """
        )

    where_sql = " AND ".join(where_parts)

    sql = f"""
        SELECT
            i.item_id,
            i.business_id,
            (to_jsonb(i)->>'title') AS title,
            (to_jsonb(i)->>'sku') AS sku,
            (to_jsonb(i)->>'brand') AS brand,
            (to_jsonb(i)->>'size') AS size,
            (to_jsonb(i)->>'status') AS status,
            i.created_at,
            i.active_at,
            i.sold_at,
            i.archived_at,
            i.status_updated_at,
            GREATEST(
                0,
                FLOOR(
                    DATE_PART(
                        'day',
                        NOW() - COALESCE(i.active_at, i.created_at)
                    )
                )
            )::int AS age_days
        FROM items i
        WHERE {where_sql}
        ORDER BY age_days DESC, i.created_at ASC NULLS LAST, i.item_id ASC
        LIMIT :limit OFFSET :offset;
    """

    rows = _rows_as_dicts(_execute(db, sql, params))
    return rows