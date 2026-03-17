from __future__ import annotations

import inspect
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.business.repo import ensure_business_settings
from app.items.repo import (
    fetch_inventory_aging_rows,
    fetch_inventory_status_summary,
    fetch_items_stats,
    fetch_one_item_scoped,
    get_items_columns as repo_get_items_columns,
    insert_item_event_scoped,
    restore_item_scoped,
    soft_delete_item_scoped,
)
from app.items.schemas import (
    InventoryAgingResponse,
    InventoryStatusSummaryResponse,
    InventoryStatusSummaryRow,
    ItemAgingRow,
    ItemsStatsResponse,
)
from app.services.pricing import PricingInputs, compute_pricing
from app.services.safety_service import evaluate_safe_to_sell
from app.services.state_machine import (
    normalize_status,
    validate_restore,
    validate_soft_delete,
    validate_user_status_change,
)

from app.ledger.service import record_buy_cost_adjustment, record_sale_entries
from app.services.marketplace_service import resolve_marketplace_for_sold_item


# ---------------------------------------------------------------------------
# Repo compatibility: item_events insert helper
# ---------------------------------------------------------------------------

def insert_item_event(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    event_type: str,
    details: Dict[str, Any],
) -> None:
    fn = insert_item_event_scoped
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    param_names = {p.name for p in params}

    details_dict = details
    details_json = json.dumps(details_dict, default=str)

    def _try_call(*args, **kwargs) -> bool:
        try:
            fn(*args, **kwargs)
            return True
        except TypeError:
            return False

    if len(params) == 2:
        candidates = [
            {
                "business_id": business_id,
                "item_id": item_id,
                "event_type": event_type,
                "details": details_dict,
            },
            {
                "business_id": business_id,
                "item_id": item_id,
                "event_type": event_type,
                "details": details_json,
            },
            {
                "business_id": business_id,
                "item_id": item_id,
                "event_type": event_type,
                "event_details": details_dict,
            },
            {
                "business_id": business_id,
                "item_id": item_id,
                "event_type": event_type,
                "event_details": details_json,
            },
        ]
        for ev in candidates:
            if _try_call(db, ev):
                return
        raise HTTPException(
            status_code=500,
            detail="insert_item_event_scoped signature not supported (event dict form).",
        )

    base: Dict[str, Any] = {}
    if "business_id" in param_names:
        base["business_id"] = business_id
    if "item_id" in param_names:
        base["item_id"] = item_id

    if "event_type" in param_names:
        base["event_type"] = event_type
    elif "type" in param_names:
        base["type"] = event_type

    if "details_json" in param_names:
        if _try_call(db, **{**base, "details_json": details_dict}):
            return
        if _try_call(db, **{**base, "details_json": details_json}):
            return

    for dk in ("details", "event_details", "payload", "data", "meta", "info"):
        if dk not in param_names:
            continue
        if _try_call(db, **{**base, dk: details_dict}):
            return
        if _try_call(db, **{**base, dk: details_json}):
            return

    raise HTTPException(
        status_code=500,
        detail=f"insert_item_event_scoped signature not supported; params={sorted(param_names)}",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_decimal(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        s = s.replace(",", ".")
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    return None


def _coerce_datetime(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
    return None


def normalize_numeric_fields(data: Dict[str, Any]) -> None:
    for k in (
        "buy_cost",
        "shipping_cost",
        "shipping_cost_paid",
        "packaging_cost",
        "platform_fee_percent",
        "promo_fee_percent",
        "multiplier",
        "target_profit",
        "market_price",
        "suggested_price",
        "min_price",
        "estimated_profit",
        "total_fee_percent",
        "sale_price",
    ):
        if k in data:
            d = parse_decimal(data.get(k))
            if d is not None:
                data[k] = d


def serialize_json_fields_for_sql(data: Dict[str, Any]) -> None:
    if "safe_to_sell_reasons" in data and isinstance(data["safe_to_sell_reasons"], dict):
        data["safe_to_sell_reasons"] = json.dumps(
            data["safe_to_sell_reasons"],
            default=str,
        )


def get_items_columns(db: Session):
    return repo_get_items_columns(db)


def _fetch_one_item_scoped_compat(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    include_deleted: bool,
) -> Optional[Dict[str, Any]]:
    fn = fetch_one_item_scoped
    sig = inspect.signature(fn)
    param_names = set(sig.parameters.keys())

    kwargs: Dict[str, Any] = {"business_id": business_id, "item_id": item_id}
    if "include_deleted" in param_names:
        kwargs["include_deleted"] = include_deleted

    try:
        return fn(db, **kwargs)  # type: ignore[arg-type]
    except TypeError:
        return fn(db, business_id=business_id, item_id=item_id)  # type: ignore[misc]


def _map_db_to_api_fields(row: Dict[str, Any]) -> None:
    if "shipping_cost" not in row and "shipping_cost_paid" in row:
        row["shipping_cost"] = row.get("shipping_cost_paid")


def get_one_item_scoped_service(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    include_deleted: bool = False,
) -> Optional[Dict[str, Any]]:
    row = _fetch_one_item_scoped_compat(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=include_deleted,
    )
    if not row:
        return None

    if isinstance(row.get("item_id"), UUID):
        row["item_id"] = str(row["item_id"])
    if isinstance(row.get("business_id"), UUID):
        row["business_id"] = str(row["business_id"])

    _map_db_to_api_fields(row)
    return row


def _clamp_limit(limit: Optional[int], *, default: int = 50, max_limit: int = 200) -> int:
    if limit is None:
        return default
    try:
        n = int(limit)
    except Exception:
        return default
    if n < 1:
        return 1
    if n > max_limit:
        return max_limit
    return n


def _sale_ledger_inserted(ledger_res: Any) -> bool:
    if not isinstance(ledger_res, dict):
        return False
    entries = ledger_res.get("entries")
    if not isinstance(entries, list):
        return False

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "SALE" and bool(entry.get("inserted")):
            return True
    return False


def _to_iso_utc(v: Any) -> Optional[str]:
    dt = _coerce_datetime(v)
    if dt is None:
        return None

    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        try:
            return str(v)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Audit events paging (deterministic cursor)
# ---------------------------------------------------------------------------

def _extract_sequence(details: Any) -> int:
    try:
        if isinstance(details, dict):
            v = details.get("sequence")
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.strip().isdigit():
                return int(v.strip())
            return 999
        if isinstance(details, str):
            d = json.loads(details)
            return _extract_sequence(d)
    except Exception:
        return 999
    return 999


def _parse_cursor(cursor: str) -> tuple[datetime, int, str]:
    try:
        parts = [p.strip() for p in cursor.split("|") if p.strip() != ""]
        if len(parts) == 2:
            created_at_s, event_id_s = parts
            seq = 999
        elif len(parts) == 3:
            created_at_s, seq_s, event_id_s = parts
            seq = int(seq_s)
        else:
            raise ValueError(
                "cursor must be created_at|event_id or created_at|sequence|event_id"
            )

        dt = datetime.fromisoformat(created_at_s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("cursor created_at must include timezone")

        _ = UUID(event_id_s)
        return dt, seq, event_id_s
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


def _cursor_to_string(dt: datetime, seq: int, event_id: Any) -> str:
    utc = dt.astimezone(timezone.utc)
    iso = utc.isoformat().replace("+00:00", "Z")
    return f"{iso}|{int(seq)}|{str(event_id)}"


def get_item_events_page(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    limit: Optional[int] = None,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    page_limit = _clamp_limit(limit)

    params: Dict[str, Any] = {
        "business_id": business_id,
        "item_id": item_id,
        "limit": page_limit + 1,
    }

    seq_expr = """
    CASE
      WHEN details IS NULL THEN 999
      WHEN jsonb_typeof(details) = 'object' AND (details ? 'sequence') THEN (details->>'sequence')::int
      ELSE 999
    END
    """

    cursor_clause = ""
    if cursor:
        cursor_created_at, cursor_seq, cursor_event_id = _parse_cursor(cursor)
        params["cursor_created_at"] = cursor_created_at
        params["cursor_seq"] = cursor_seq
        params["cursor_event_id"] = cursor_event_id
        cursor_clause = f"""
          AND (created_at, {seq_expr}, event_id) < (:cursor_created_at, :cursor_seq, :cursor_event_id::uuid)
        """

    rows = (
        db.execute(
            text(
                f"""
                SELECT event_id, business_id, item_id, event_type, details, created_at
                FROM item_events
                WHERE business_id = :business_id
                  AND item_id = :item_id
                  {cursor_clause}
                ORDER BY created_at DESC, {seq_expr} ASC, event_id DESC
                LIMIT :limit
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    has_more = len(rows) > page_limit
    page_rows = rows[:page_limit]

    events: List[Dict[str, Any]] = []
    for r in page_rows:
        d = dict(r)

        for k in ("event_id", "business_id", "item_id"):
            if isinstance(d.get(k), UUID):
                d[k] = str(d[k])

        if isinstance(d.get("details"), str):
            try:
                d["details"] = json.loads(d["details"])
            except Exception:
                pass

        events.append(d)

    next_cursor: Optional[str] = None
    if has_more and page_rows:
        last = page_rows[-1]
        last_dt = last.get("created_at")
        last_event_id = last.get("event_id")
        if last_dt is not None and last_event_id is not None:
            seq = _extract_sequence(last.get("details"))
            next_cursor = _cursor_to_string(last_dt, seq, last_event_id)

    return {
        "item_id": str(item_id),
        "events": events,
        "limit": page_limit,
        "next_cursor": next_cursor,
    }


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

def list_items_workflow(
    db: Session,
    *,
    business_id: str,
    status: Optional[str] = None,
    safe_to_sell: Optional[bool] = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    status_norm = normalize_status(status) if status is not None else None
    if status_norm == "Deleted" and not include_deleted:
        raise HTTPException(
            status_code=400,
            detail="To list Deleted items, set include_deleted=true",
        )

    cols = set(get_items_columns(db))
    order_by = "created_at DESC" if "created_at" in cols else "item_id DESC"

    params: Dict[str, Any] = {
        "limit": int(limit),
        "offset": int(offset),
        "business_id": business_id,
    }
    conditions = ["business_id = :business_id"]

    if not include_deleted:
        conditions.append("status <> 'Deleted'")

    if status is not None and str(status).strip() != "":
        conditions.append("status = :status")
        params["status"] = status

    if safe_to_sell is not None and "safe_to_sell" in cols:
        conditions.append("safe_to_sell = :safe_to_sell")
        params["safe_to_sell"] = safe_to_sell

    where = "WHERE " + " AND ".join(conditions)

    rows = (
        db.execute(
            text(
                f"""
                SELECT *
                FROM items
                {where}
                ORDER BY {order_by}
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    items = [dict(r) for r in rows]
    for it in items:
        _map_db_to_api_fields(it)

    return {
        "items": items,
        "limit": int(limit),
        "offset": int(offset),
        "include_deleted": bool(include_deleted),
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _fetch_items_stats_compat(
    db: Session,
    *,
    business_id: str,
    status: Any = None,
    safe_to_sell: Any = None,
    include_deleted: bool = False,
) -> Dict[str, Any]:
    status_norm = normalize_status(str(status)) if status is not None else None
    if status_norm == "Deleted" and not include_deleted:
        raise HTTPException(
            status_code=400,
            detail="To query Deleted items in stats, set include_deleted=true",
        )

    fn = fetch_items_stats
    sig = inspect.signature(fn)
    param_names = set(sig.parameters.keys())

    kwargs: Dict[str, Any] = {
        "business_id": business_id,
        "status": status,
        "safe_to_sell": safe_to_sell,
    }
    if "include_deleted" in param_names:
        kwargs["include_deleted"] = include_deleted

    try:
        return fn(db, **kwargs)  # type: ignore[arg-type]
    except TypeError:
        return fn(db, business_id=business_id, status=status, safe_to_sell=safe_to_sell)  # type: ignore[misc]


def get_items_stats(
    db: Session,
    *,
    business_id: str,
    status=None,
    safe_to_sell=None,
    include_deleted: bool = False,
):
    data = _fetch_items_stats_compat(
        db,
        business_id=business_id,
        status=status,
        safe_to_sell=safe_to_sell,
        include_deleted=include_deleted,
    )
    return ItemsStatsResponse(**data)


# ---------------------------------------------------------------------------
# Inventory intelligence
# ---------------------------------------------------------------------------

def get_inventory_status_summary(
    db: Session,
    *,
    business_id: str,
    include_deleted: bool = False,
) -> InventoryStatusSummaryResponse:
    data = fetch_inventory_status_summary(
        db,
        business_id=business_id,
        include_deleted=include_deleted,
    )

    rows = [
        InventoryStatusSummaryRow(status=status, count=count)
        for status, count in sorted((data.get("by_status") or {}).items(), key=lambda x: x[0])
    ]

    return InventoryStatusSummaryResponse(
        business_id=business_id,
        include_deleted=include_deleted,
        total_items=int(data.get("total_items") or 0),
        rows=rows,
    )


def get_inventory_aging(
    db: Session,
    *,
    business_id: str,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> InventoryAgingResponse:
    limit_i = _clamp_limit(limit, default=50, max_limit=200)
    offset_i = max(0, int(offset))

    rows = fetch_inventory_aging_rows(
        db,
        business_id=business_id,
        include_deleted=include_deleted,
        only_active=False,
        min_age_days=None,
        limit=limit_i,
        offset=offset_i,
    )

    out_rows: List[ItemAgingRow] = []
    for r in rows:
        out_rows.append(
            ItemAgingRow(
                item_id=str(r.get("item_id")),
                business_id=str(r.get("business_id")),
                title=r.get("title"),
                sku=r.get("sku"),
                brand=r.get("brand"),
                size=r.get("size"),
                status=r.get("status"),
                created_at=_to_iso_utc(r.get("created_at")),
                active_at=_to_iso_utc(r.get("active_at")),
                sold_at=_to_iso_utc(r.get("sold_at")),
                archived_at=_to_iso_utc(r.get("archived_at")),
                status_updated_at=_to_iso_utc(r.get("status_updated_at")),
                age_days=int(r.get("age_days") or 0),
            )
        )

    return InventoryAgingResponse(
        business_id=business_id,
        include_deleted=include_deleted,
        only_active=False,
        min_age_days=None,
        limit=limit_i,
        offset=offset_i,
        rows=out_rows,
    )


def get_dead_stock_items(
    db: Session,
    *,
    business_id: str,
    min_age_days: int = 30,
    limit: int = 50,
    offset: int = 0,
) -> InventoryAgingResponse:
    try:
        min_age_i = int(min_age_days)
    except Exception:
        min_age_i = 30
    min_age_i = max(1, min(min_age_i, 3650))

    limit_i = _clamp_limit(limit, default=50, max_limit=200)
    offset_i = max(0, int(offset))

    rows = fetch_inventory_aging_rows(
        db,
        business_id=business_id,
        include_deleted=False,
        only_active=True,
        min_age_days=min_age_i,
        limit=limit_i,
        offset=offset_i,
    )

    out_rows: List[ItemAgingRow] = []
    for r in rows:
        out_rows.append(
            ItemAgingRow(
                item_id=str(r.get("item_id")),
                business_id=str(r.get("business_id")),
                title=r.get("title"),
                sku=r.get("sku"),
                brand=r.get("brand"),
                size=r.get("size"),
                status=r.get("status"),
                created_at=_to_iso_utc(r.get("created_at")),
                active_at=_to_iso_utc(r.get("active_at")),
                sold_at=_to_iso_utc(r.get("sold_at")),
                archived_at=_to_iso_utc(r.get("archived_at")),
                status_updated_at=_to_iso_utc(r.get("status_updated_at")),
                age_days=int(r.get("age_days") or 0),
            )
        )

    return InventoryAgingResponse(
        business_id=business_id,
        include_deleted=False,
        only_active=True,
        min_age_days=min_age_i,
        limit=limit_i,
        offset=offset_i,
        rows=out_rows,
    )


# ---------------------------------------------------------------------------
# Pricing snapshot computation (stored snapshot)
# ---------------------------------------------------------------------------

def compute_snapshot_from_business_defaults(
    item_data: Dict[str, Any],
    settings,
    *,
    market_price_override: Optional[Decimal] = None,
) -> Dict[str, Any]:
    if not settings:
        return {}

    buy_cost = parse_decimal(item_data.get("buy_cost"))
    multiplier = parse_decimal(item_data.get("multiplier"))

    shipping_cost = parse_decimal(getattr(settings, "default_shipping_cost", None))
    packaging_cost = parse_decimal(getattr(settings, "default_packaging_cost", None))
    target_profit = parse_decimal(getattr(settings, "target_profit", None))
    ebay_fee_percent = parse_decimal(getattr(settings, "platform_fee_percent", None))
    promo_percent = parse_decimal(getattr(settings, "promo_fee_percent", None))
    rounding_mode = getattr(settings, "rounding_mode", None)

    required = [
        buy_cost,
        multiplier,
        shipping_cost,
        packaging_cost,
        target_profit,
        ebay_fee_percent,
        promo_percent,
        rounding_mode,
    ]
    if any(x is None for x in required):
        return {}

    rm = str(rounding_mode).upper()
    rounding_mode_norm = "END_99" if rm in ("END_99", "END99", "99") else "NONE"

    res = compute_pricing(
        PricingInputs(
            buy_cost=buy_cost,
            demand_multiplier=multiplier,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
            target_profit=target_profit,
            ebay_fee_percent=ebay_fee_percent,
            promo_percent=promo_percent,
            rounding_mode=rounding_mode_norm,
        )
    )

    snapshot: Dict[str, Any] = {
        "suggested_price": res.suggested_price,
        "min_price": res.min_price,
        "estimated_profit": res.estimated_profit,
        "total_fee_percent": res.total_fee_percent,
        "market_price": (
            market_price_override
            if market_price_override is not None
            else res.market_price
        ),
    }

    safety = evaluate_safe_to_sell(
        suggested_price=parse_decimal(snapshot["suggested_price"]) or Decimal("0"),
        min_price=parse_decimal(snapshot["min_price"]) or Decimal("0"),
        estimated_profit=parse_decimal(snapshot["estimated_profit"]) or Decimal("0"),
        target_profit=target_profit or Decimal("0"),
        market_price=parse_decimal(snapshot.get("market_price")),
        require_market_price=False,
        enforce_market_floor=True,
    )

    snapshot["safe_to_sell"] = safety.safe_to_sell
    snapshot["safe_to_sell_reasons"] = {
        "reasons": [r.value for r in safety.reasons],
        "version": 1,
    }
    return snapshot


_ECON_FIELDS = (
    "buy_cost",
    "multiplier",
    "suggested_price",
    "min_price",
    "estimated_profit",
    "total_fee_percent",
    "safe_to_sell",
    "market_price",
)


def _extract_econ_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: row.get(k) for k in _ECON_FIELDS}


def _emit_econ_updated(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    before_row: Dict[str, Any],
    after_row: Dict[str, Any],
    trigger: str,
) -> None:
    before = _extract_econ_snapshot(before_row)
    after = _extract_econ_snapshot(after_row)
    changed = [k for k in _ECON_FIELDS if before.get(k) != after.get(k)]
    if not changed:
        return
    insert_item_event(
        db,
        business_id=business_id,
        item_id=item_id,
        event_type="ECON_UPDATED",
        details={
            "trigger": trigger,
            "changed_fields": changed,
            "before": before,
            "after": after,
        },
    )


# ---------------------------------------------------------------------------
# Soft delete / restore workflows
# ---------------------------------------------------------------------------

def soft_delete_item_workflow(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    current = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    if not current:
        raise HTTPException(status_code=404, detail="Item not found")

    old_status_raw = current.get("status")
    old_status = normalize_status(str(old_status_raw)) or str(old_status_raw or "")

    if old_status == "Deleted":
        return {
            "deleted": True,
            "soft": True,
            "item_id": item_id,
            "status": "Deleted",
            "deleted_at": current.get("deleted_at"),
            "deleted_by": current.get("deleted_by"),
        }

    try:
        validate_soft_delete(old_status)
    except ValueError as e:
        if old_status == "Sold":
            insert_item_event(
                db,
                business_id=business_id,
                item_id=item_id,
                event_type="SOLD_DELETE_BLOCKED",
                details={
                    "trigger": "ITEM_SOFT_DELETE",
                    "old_status": old_status,
                    "attempted_status": "Deleted",
                    "deleted_by": actor_user_id,
                    "actor_user_id": actor_user_id,
                    "sequence": 1,
                },
            )
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Cannot delete item after it is Sold",
            )
        raise HTTPException(status_code=400, detail=str(e))

    affected = soft_delete_item_scoped(
        db,
        business_id=business_id,
        item_id=item_id,
        deleted_by=actor_user_id,
    )
    if affected != 1:
        raise HTTPException(status_code=404, detail="Item not found")

    insert_item_event(
        db,
        business_id=business_id,
        item_id=item_id,
        event_type="ITEM_SOFT_DELETED",
        details={
            "trigger": "ITEM_SOFT_DELETE",
            "old_status": old_status,
            "new_status": "Deleted",
            "deleted_by": actor_user_id,
            "actor_user_id": actor_user_id,
            "sequence": 1,
        },
    )
    insert_item_event(
        db,
        business_id=business_id,
        item_id=item_id,
        event_type="STATUS_CHANGED",
        details={
            "trigger": "ITEM_SOFT_DELETE",
            "old_status": old_status,
            "new_status": "Deleted",
            "deleted_by": actor_user_id,
            "actor_user_id": actor_user_id,
            "sequence": 2,
        },
    )

    db.commit()
    after = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    return {
        "deleted": True,
        "soft": True,
        "item_id": item_id,
        "status": "Deleted",
        "deleted_at": after.get("deleted_at") if after else None,
        "deleted_by": after.get("deleted_by") if after else None,
    }


def restore_item_workflow(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    current = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    if not current:
        raise HTTPException(status_code=404, detail="Item not found")

    old_status_raw = current.get("status")
    old_status = normalize_status(str(old_status_raw)) or str(old_status_raw or "")

    try:
        validate_restore(old_status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    affected = restore_item_scoped(
        db,
        business_id=business_id,
        item_id=item_id,
        restored_by=actor_user_id,
    )
    if affected != 1:
        raise HTTPException(status_code=404, detail="Item not found or not Deleted")

    insert_item_event(
        db,
        business_id=business_id,
        item_id=item_id,
        event_type="ITEM_RESTORED",
        details={
            "trigger": "ITEM_RESTORE",
            "old_status": "Deleted",
            "new_status": "Archived",
            "restored_by": actor_user_id,
            "actor_user_id": actor_user_id,
            "sequence": 1,
        },
    )
    insert_item_event(
        db,
        business_id=business_id,
        item_id=item_id,
        event_type="STATUS_CHANGED",
        details={
            "trigger": "ITEM_RESTORE",
            "old_status": "Deleted",
            "new_status": "Archived",
            "restored_by": actor_user_id,
            "actor_user_id": actor_user_id,
            "sequence": 2,
        },
    )

    db.commit()
    after = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    return {
        "restored": True,
        "item_id": item_id,
        "status": "Archived",
        "deleted_at": after.get("deleted_at") if after else None,
        "restored_by": after.get("restored_by") if after else None,
    }


# ---------------------------------------------------------------------------
# Create / Update / Bulk Recalc
# ---------------------------------------------------------------------------

def create_item_workflow(
    db: Session,
    *,
    business_id: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    cols = set(get_items_columns(db))
    settings = ensure_business_settings(db, business_id=business_id)

    item_id = str(uuid.uuid4())
    now = now_utc()

    insert_data: Dict[str, Any] = {"item_id": item_id, "business_id": business_id}

    if "created_at" in cols:
        insert_data["created_at"] = now
    if "updated_at" in cols:
        insert_data["updated_at"] = now

    if "shipping_cost" in data and "shipping_cost_paid" in cols:
        insert_data["shipping_cost_paid"] = data.get("shipping_cost")

    for k, v in data.items():
        if k in cols:
            insert_data[k] = v

    normalize_numeric_fields(insert_data)

    market_override = (
        parse_decimal(insert_data.get("market_price"))
        if "market_price" in insert_data
        else None
    )
    snapshot = compute_snapshot_from_business_defaults(
        insert_data,
        settings,
        market_price_override=market_override,
    )

    for k, v in snapshot.items():
        if k in cols:
            insert_data[k] = v

    serialize_json_fields_for_sql(insert_data)

    insert_cols = sorted(insert_data.keys())
    col_list = ", ".join(insert_cols)
    val_list = ", ".join([f":{c}" for c in insert_cols])

    db.execute(text(f"INSERT INTO items ({col_list}) VALUES ({val_list})"), insert_data)
    db.flush()

    row = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    if not row:
        raise HTTPException(
            status_code=500,
            detail="Create failed (item not found after insert).",
        )

    buy_cost = parse_decimal(row.get("buy_cost"))
    if buy_cost is not None and buy_cost > Decimal("0"):
        created_at = _coerce_datetime(row.get("created_at")) or now
        adj = record_buy_cost_adjustment(
            db,
            business_id=business_id,
            item_id=item_id,
            old_buy_cost=Decimal("0"),
            new_buy_cost=buy_cost,
            occurred_at=created_at,
            actor_user_id=None,
            currency=str(getattr(settings, "currency", None) or "EUR"),
        )
        if adj:
            insert_item_event(
                db,
                business_id=business_id,
                item_id=item_id,
                event_type="LEDGER_APPENDED",
                details={"trigger": "ITEM_CREATED", "entry": adj, "sequence": 40},
            )

    db.commit()
    row = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    if not row:
        raise HTTPException(
            status_code=500,
            detail="Create failed (item not found after commit).",
        )
    return row


def update_item_workflow(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    patch: Dict[str, Any],
    actor_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    cols = set(get_items_columns(db))
    settings = ensure_business_settings(db, business_id=business_id)

    current = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    if not current:
        raise HTTPException(status_code=404, detail="Item not found")

    old_status_raw = current.get("status")
    old_status_norm = normalize_status(str(old_status_raw)) or str(old_status_raw or "")

    if old_status_norm == "Deleted":
        forbidden = sorted(patch.keys())
        insert_item_event(
            db,
            business_id=business_id,
            item_id=item_id,
            event_type="DELETED_EDIT_BLOCKED",
            details={
                "trigger": "ITEM_UPDATED",
                "old_status": "Deleted",
                "forbidden_fields": forbidden,
                "actor_user_id": actor_user_id,
                "sequence": 1,
            },
        )
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="This item is Deleted and cannot be edited. Restore it first.",
        )

    old_status = current.get("status")
    requested_new_status = patch.get("status", old_status)
    status_changed = requested_new_status is not None and requested_new_status != old_status

    if old_status == "Sold" and "buy_cost" in patch:
        insert_item_event(
            db,
            business_id=business_id,
            item_id=item_id,
            event_type="SOLD_EDIT_BLOCKED",
            details={
                "payload": patch,
                "forbidden_fields": ["buy_cost"],
                "actor_user_id": actor_user_id,
            },
        )
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="These fields are not editable after an item is Sold: buy_cost",
        )

    if "status" in patch:
        new_norm = normalize_status(str(patch.get("status")))
        if new_norm == "Deleted":
            insert_item_event(
                db,
                business_id=business_id,
                item_id=item_id,
                event_type="DELETED_STATUS_CHANGE_BLOCKED",
                details={
                    "trigger": "ITEM_UPDATED",
                    "old_status": old_status_norm,
                    "attempted_status": "Deleted",
                    "actor_user_id": actor_user_id,
                    "sequence": 1,
                },
            )
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Use the delete endpoint to move an item to Deleted.",
            )

    old_buy_cost = current.get("buy_cost")
    new_buy_cost = patch.get("buy_cost", old_buy_cost)
    buy_cost_changed = "buy_cost" in patch and parse_decimal(old_buy_cost) != parse_decimal(new_buy_cost)

    if status_changed:
        try:
            validate_user_status_change(str(old_status), str(requested_new_status))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    effective = dict(current)
    effective.update(patch)
    normalize_numeric_fields(effective)

    market_override = (
        parse_decimal(patch.get("market_price")) if "market_price" in patch else None
    )
    snapshot = compute_snapshot_from_business_defaults(
        effective,
        settings,
        market_price_override=market_override,
    )

    update_data: Dict[str, Any] = {k: v for k, v in patch.items() if k in cols}

    if "shipping_cost" in patch and "shipping_cost_paid" in cols:
        update_data["shipping_cost_paid"] = patch.get("shipping_cost")

    new_status_norm = (
        normalize_status(str(requested_new_status))
        if requested_new_status is not None
        else None
    )

    if status_changed and new_status_norm == "Sold":
        if "sold_at" in cols and "sold_at" not in update_data:
            update_data["sold_at"] = now_utc()

    for k, v in snapshot.items():
        if k in cols:
            update_data[k] = v

    update_now = now_utc()
    if "updated_at" in cols:
        update_data["updated_at"] = update_now
    if status_changed and "status_updated_at" in cols:
        update_data["status_updated_at"] = update_now

    normalize_numeric_fields(update_data)
    serialize_json_fields_for_sql(update_data)

    if not update_data:
        return current

    set_clause = ", ".join([f"{k} = :{k}" for k in sorted(update_data.keys())])
    params = dict(update_data)
    params["business_id"] = business_id
    params["item_id"] = item_id

    db.execute(
        text(
            f"""
            UPDATE items
            SET {set_clause}
            WHERE business_id = :business_id
              AND item_id = :item_id
            """
        ),
        params,
    )
    db.flush()

    after = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    if not after:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Update failed (item not found after update).",
        )

    _emit_econ_updated(
        db,
        business_id=business_id,
        item_id=item_id,
        before_row=current,
        after_row=after,
        trigger="ITEM_UPDATED",
    )

    if status_changed:
        insert_item_event(
            db,
            business_id=business_id,
            item_id=item_id,
            event_type="STATUS_CHANGED",
            details={
                "trigger": "ITEM_UPDATED",
                "old_status": old_status,
                "new_status": requested_new_status,
                "actor_user_id": actor_user_id,
            },
        )

    if buy_cost_changed and old_status_norm != "Sold":
        adj = record_buy_cost_adjustment(
            db,
            business_id=business_id,
            item_id=item_id,
            old_buy_cost=old_buy_cost,
            new_buy_cost=new_buy_cost,
            occurred_at=_coerce_datetime(after.get("updated_at")) or now_utc(),
            actor_user_id=actor_user_id,
            currency=str(getattr(settings, "currency", None) or "EUR"),
        )
        if adj:
            insert_item_event(
                db,
                business_id=business_id,
                item_id=item_id,
                event_type="LEDGER_APPENDED",
                details={
                    "trigger": "BUY_COST_CHANGED",
                    "entry": adj,
                    "sequence": 50,
                },
            )

    if status_changed and new_status_norm == "Sold":
        sold_at = _coerce_datetime(after.get("sold_at")) or _coerce_datetime(
            update_data.get("sold_at")
        )
        ship_paid = after.get("shipping_cost_paid")
        if ship_paid is None:
            ship_paid = after.get("shipping_cost")

        marketplace = resolve_marketplace_for_sold_item(
            db,
            business_id=business_id,
            item_id=item_id,
            explicit_marketplace=patch.get("marketplace"),
        )

        ledger_res = record_sale_entries(
            db,
            business_id=business_id,
            item_id=item_id,
            sale_price=after.get("sale_price"),
            sold_at=sold_at,
            actor_user_id=actor_user_id,
            total_fee_percent=after.get("total_fee_percent"),
            shipping_cost_paid=ship_paid,
            currency=str(getattr(settings, "currency", None) or "EUR"),
            marketplace_source=marketplace,
        )
        db.flush()

        if not _sale_ledger_inserted(ledger_res):
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=(
                    "Sold transition did not create SALE ledger entry. "
                    f"ledger_result={ledger_res}"
                ),
            )

        insert_item_event(
            db,
            business_id=business_id,
            item_id=item_id,
            event_type="LEDGER_APPENDED",
            details={
                "trigger": "ITEM_SOLD",
                "result": ledger_res,
                "marketplace": marketplace,
                "sequence": 60,
            },
        )
        insert_item_event(
            db,
            business_id=business_id,
            item_id=item_id,
            event_type="SALE_RECORDED",
            details={
                "trigger": "ITEM_SOLD",
                "sold_at": sold_at.isoformat() if sold_at else None,
                "sale_price": after.get("sale_price"),
                "marketplace": marketplace,
                "sequence": 61,
            },
        )

    db.commit()

    after = get_one_item_scoped_service(
        db,
        business_id=business_id,
        item_id=item_id,
        include_deleted=True,
    )
    if not after:
        raise HTTPException(
            status_code=500,
            detail="Update committed but item could not be reloaded.",
        )
    return after


def bulk_recalculate_snapshots(
    db: Session,
    *,
    business_id: str,
) -> Dict[str, Any]:
    cols = set(get_items_columns(db))
    settings = ensure_business_settings(db, business_id=business_id)

    item_rows = (
        db.execute(
            text(
                """
                SELECT item_id
                FROM items
                WHERE business_id = :business_id
                  AND status <> 'Deleted'
                """
            ),
            {"business_id": business_id},
        )
        .mappings()
        .all()
    )

    updated = 0
    for r in item_rows:
        item_id = str(r["item_id"])
        current = get_one_item_scoped_service(
            db,
            business_id=business_id,
            item_id=item_id,
            include_deleted=True,
        )
        if not current:
            continue

        status_norm = normalize_status(str(current.get("status")))
        if status_norm == "Deleted":
            continue

        effective = dict(current)
        normalize_numeric_fields(effective)

        snapshot = compute_snapshot_from_business_defaults(
            effective,
            settings,
            market_price_override=parse_decimal(effective.get("market_price")),
        )

        update_data: Dict[str, Any] = {}
        for k, v in snapshot.items():
            if k in cols:
                update_data[k] = v

        if "updated_at" in cols:
            update_data["updated_at"] = now_utc()

        normalize_numeric_fields(update_data)
        serialize_json_fields_for_sql(update_data)

        if not update_data:
            continue

        set_clause = ", ".join([f"{k} = :{k}" for k in sorted(update_data.keys())])
        params = dict(update_data)
        params["business_id"] = business_id
        params["item_id"] = item_id

        db.execute(
            text(
                f"""
                UPDATE items
                SET {set_clause}
                WHERE business_id = :business_id
                  AND item_id = :item_id
                """
            ),
            params,
        )

        after = get_one_item_scoped_service(
            db,
            business_id=business_id,
            item_id=item_id,
            include_deleted=True,
        )
        if after:
            _emit_econ_updated(
                db,
                business_id=business_id,
                item_id=item_id,
                before_row=current,
                after_row=after,
                trigger="BULK_RECALC",
            )

        updated += 1

    db.commit()
    return {"business_id": business_id, "updated_items": updated}