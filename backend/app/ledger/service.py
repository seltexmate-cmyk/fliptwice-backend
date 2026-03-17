# backend/app/ledger/service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import logging

from app.ledger.repo import (
    fetch_business_entry_type_totals,
    fetch_business_sold_count,
    fetch_item_ledger_entries,
    fetch_item_ledger_totals,
    insert_ledger_entry_scoped,
)

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

ENTRY_BUY = "BUY"
ENTRY_BUY_ADJUSTMENT = "BUY_ADJUSTMENT"
ENTRY_SALE = "SALE"
ENTRY_FEE = "FEE"
ENTRY_SHIPPING_COST = "SHIPPING_COST"
ENTRY_REFUND = "REFUND"
ENTRY_ADJUSTMENT = "ADJUSTMENT"

LEDGER_SOURCES = {
    "SYSTEM",
    "MANUAL",
    "IMPORT_EBAY",
    # Marketplaces (sale-related entries should use these when resolved)
    "EBAY",
    "VINTED",
    "DEPOP",
    "POSHMARK",
    "GRAILED",
    "ETSY",
    "SHOPIFY",
    "OTHER",
}
_PG_UNIQUE_VIOLATION = "23505"


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


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_source(source: str) -> str:
    s = str(source or "").strip().upper()
    if s == "":
        return "SYSTEM"
    if s not in LEDGER_SOURCES:
        raise HTTPException(status_code=400, detail=f"Invalid ledger source: {source!r}")
    return s


def _ensure_uuidish(v: Optional[str], field: str) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    return s


def _signed_amount(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01")))


def _normalize_source_ref(source_ref: Optional[str]) -> Optional[str]:
    if source_ref is None:
        return None
    s = str(source_ref).strip()
    return s if s != "" else None


def _is_unique_violation(err: IntegrityError) -> bool:
    orig = getattr(err, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    if pgcode == _PG_UNIQUE_VIOLATION:
        return True
    msg = str(orig or "").lower()
    return "duplicate key value violates unique constraint" in msg


def _parse_start_end(start: str, end: str) -> Tuple[datetime, datetime]:
    """
    Accepts:
      - YYYY-MM-DD (treated as UTC midnight)
      - ISO8601 datetime (timezone-aware preferred; naive treated as UTC)
    Returns (start_dt, end_dt) in UTC with end > start.
    """
    def parse_one(x: str, label: str) -> datetime:
        s = str(x or "").strip()
        if not s:
            raise HTTPException(status_code=400, detail=f"{label} is required")

        # Date-only
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            try:
                d = date.fromisoformat(s)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid {label} date: {s!r}")
            return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)

        # Datetime
        try:
            # Handle trailing Z
            if s.endswith("Z"):
                s2 = s[:-1] + "+00:00"
            else:
                s2 = s
            dt = datetime.fromisoformat(s2)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid {label} datetime: {s!r}")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    start_dt = parse_one(start, "start")
    end_dt = parse_one(end, "end")

    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end must be after start")

    return start_dt, end_dt


# ---------------------------------------------------------------------------
# Idempotent append
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppendResult:
    inserted: bool
    entry_id: Optional[str]
    reason: Optional[str] = None


def append_ledger_entry_idempotent(
    db: Session,
    *,
    business_id: str,
    item_id: Optional[str],
    entry_type: str,
    amount: Decimal,
    currency: str = "EUR",
    occurred_at: Optional[datetime] = None,
    actor_user_id: Optional[str] = None,
    source: str = "SYSTEM",
    source_ref: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AppendResult:
    if occurred_at is None:
        occurred_at = now_utc()

    business_id_norm = _ensure_uuidish(business_id, "business_id") or ""
    if business_id_norm == "":
        raise HTTPException(status_code=400, detail="business_id is required")

    item_id_norm = _ensure_uuidish(item_id, "item_id")
    actor_user_id_norm = _ensure_uuidish(actor_user_id, "actor_user_id")
    source_norm = _require_source(source)
    source_ref_norm = _normalize_source_ref(source_ref)

    try:
        r = insert_ledger_entry_scoped(
            db,
            business_id=business_id_norm,
            item_id=item_id_norm,
            entry_type=str(entry_type),
            amount=_signed_amount(amount),
            currency=str(currency or "EUR"),
            occurred_at_iso=_iso(occurred_at),
            actor_user_id=actor_user_id_norm,
            source=source_norm,
            source_ref=source_ref_norm,
            details=details,
        )

        # If the repo says "not inserted" but also didn't return an existing id,
        # treat it as a failure (otherwise sold items can silently produce no rows).
        entry_id = (str(r.entry_id).strip() if r.entry_id is not None else "")
        if not r.inserted and source_ref_norm is not None and entry_id == "":
            raise RuntimeError(
                "Ledger insert returned inserted=False but no entry_id; "
                f"business_id={business_id_norm} item_id={item_id_norm} entry_type={entry_type} source_ref={source_ref_norm}"
            )

        return AppendResult(
            inserted=bool(r.inserted),
            entry_id=entry_id or None,
            reason=None if r.inserted else "DUPLICATE_SOURCE_REF",
        )
    except IntegrityError as ie:
        # Safety net; duplicates should normally be handled by ON CONFLICT.
        # IMPORTANT: only treat as duplicate when we have a source_ref (idempotency key).
        if source_ref_norm is not None and _is_unique_violation(ie):
            db.rollback()
            logging.getLogger(__name__).info(
                "Ledger duplicate suppressed (unique violation): business_id=%s item_id=%s entry_type=%s source_ref=%s",
                business_id_norm,
                item_id_norm,
                entry_type,
                source_ref_norm,
            )
            return AppendResult(inserted=False, entry_id=None, reason="DUPLICATE_SOURCE_REF")
        raise
    except HTTPException:
        raise
    except Exception:
        # Do not swallow failures silently; log with context and re-raise.
        logging.getLogger(__name__).exception(
            "Ledger insert failed: business_id=%s item_id=%s entry_type=%s source_ref=%s",
            business_id_norm,
            item_id_norm,
            entry_type,
            source_ref_norm,
        )
        raise


# ---------------------------------------------------------------------------
# Business operations to be called from item lifecycle
# ---------------------------------------------------------------------------

def record_sale_entries(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    sale_price: Any,
    sold_at: Optional[datetime],
    actor_user_id: Optional[str],
    total_fee_percent: Any = None,
    shipping_cost_paid: Any = None,
    currency: str = "EUR",
    marketplace_source: str = "SYSTEM",
) -> Dict[str, Any]:
    sale = parse_decimal(sale_price)
    if sale is None:
        raise HTTPException(status_code=400, detail="Cannot record SALE ledger entry: sale_price missing/invalid.")

    sold_dt = sold_at or now_utc()
    sold_iso = _iso(sold_dt)
    source_ref_base = f"SALE:{item_id}:{sold_iso}"

    results: Dict[str, Any] = {"source_ref": source_ref_base, "entries": []}

    r_sale = append_ledger_entry_idempotent(
        db,
        business_id=business_id,
        item_id=item_id,
        entry_type=ENTRY_SALE,
        amount=+sale,
        currency=currency,
        occurred_at=sold_dt,
        actor_user_id=actor_user_id,
        source=marketplace_source,
        source_ref=source_ref_base,
        details={"kind": "SALE", "sold_at": sold_iso, "marketplace": marketplace_source},
    )
    results["entries"].append({"type": ENTRY_SALE, "inserted": r_sale.inserted, "entry_id": r_sale.entry_id})

    fee_pct = parse_decimal(total_fee_percent)
    if fee_pct is not None:
        fee_amount = (sale * fee_pct / Decimal("100")).quantize(Decimal("0.01"))
        if fee_amount != Decimal("0.00"):
            r_fee = append_ledger_entry_idempotent(
                db,
                business_id=business_id,
                item_id=item_id,
                entry_type=ENTRY_FEE,
                amount=-fee_amount,
                currency=currency,
                occurred_at=sold_dt,
                actor_user_id=actor_user_id,
                source=marketplace_source,
                source_ref=f"{source_ref_base}:FEE",
                details={"kind": "FEE", "percent": str(fee_pct), "marketplace": marketplace_source},
            )
            results["entries"].append({"type": ENTRY_FEE, "inserted": r_fee.inserted, "entry_id": r_fee.entry_id})

    ship = parse_decimal(shipping_cost_paid)
    if ship is not None and ship != Decimal("0"):
        r_ship = append_ledger_entry_idempotent(
            db,
            business_id=business_id,
            item_id=item_id,
            entry_type=ENTRY_SHIPPING_COST,
            amount=-ship,
            currency=currency,
            occurred_at=sold_dt,
            actor_user_id=actor_user_id,
            source=marketplace_source,
            source_ref=f"{source_ref_base}:SHIPPING",
            details={"kind": "SHIPPING_COST", "marketplace": marketplace_source},
        )
        results["entries"].append({"type": ENTRY_SHIPPING_COST, "inserted": r_ship.inserted, "entry_id": r_ship.entry_id})

    return results


def record_buy_cost_adjustment(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    old_buy_cost: Any,
    new_buy_cost: Any,
    occurred_at: Optional[datetime],
    actor_user_id: Optional[str],
    currency: str = "EUR",
    source_ref: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    old_v = parse_decimal(old_buy_cost)
    new_v = parse_decimal(new_buy_cost)
    if old_v is None or new_v is None:
        return None

    delta = (new_v - old_v).quantize(Decimal("0.01"))
    if delta == Decimal("0.00"):
        return None

    occ = occurred_at or now_utc()
    occ_iso = _iso(occ)

    derived_ref = f"BUY_ADJ:{item_id}:{occ_iso}:{str(old_v)}->{str(new_v)}"
    source_ref_norm = _normalize_source_ref(source_ref) or derived_ref

    amount = -delta  # cost up => negative; cost down => positive

    r = append_ledger_entry_idempotent(
        db,
        business_id=business_id,
        item_id=item_id,
        entry_type=ENTRY_BUY_ADJUSTMENT,
        amount=amount,
        currency=currency,
        occurred_at=occ,
        actor_user_id=actor_user_id,
        source="SYSTEM",
        source_ref=source_ref_norm,
        details={"kind": "BUY_COST_ADJUSTMENT", "old_buy_cost": str(old_v), "new_buy_cost": str(new_v)},
    )
    return {"type": ENTRY_BUY_ADJUSTMENT, "inserted": r.inserted, "entry_id": r.entry_id, "source_ref": source_ref_norm}


# ---------------------------------------------------------------------------
# Profit summary API (business-level)
# ---------------------------------------------------------------------------

def get_business_profit_summary(
    db: Session,
    *,
    business_id: str,
    start: str,
    end: str,
) -> Dict[str, Any]:
    business_id_norm = _ensure_uuidish(business_id, "business_id") or ""
    if business_id_norm == "":
        raise HTTPException(status_code=400, detail="business_id is required")

    start_dt, end_dt = _parse_start_end(start, end)
    start_iso = _iso(start_dt)
    end_iso = _iso(end_dt)

    tracked_types = [ENTRY_SALE, ENTRY_FEE, ENTRY_SHIPPING_COST, ENTRY_BUY_ADJUSTMENT]

    rows = fetch_business_entry_type_totals(
        db,
        business_id=business_id_norm,
        start_iso=start_iso,
        end_iso=end_iso,
        entry_types=tracked_types,
    )

    by_type: Dict[str, Dict[str, Any]] = {t: {"total_amount": Decimal("0.00"), "entry_count": 0} for t in tracked_types}
    for r in rows:
        t = str(r.get("entry_type") or "")
        if t not in by_type:
            continue
        by_type[t]["total_amount"] = Decimal(str(r.get("total_amount") or "0"))
        by_type[t]["entry_count"] = int(r.get("entry_count") or 0)

    revenue = by_type[ENTRY_SALE]["total_amount"]
    fees = by_type[ENTRY_FEE]["total_amount"]
    shipping = by_type[ENTRY_SHIPPING_COST]["total_amount"]
    buy_costs = by_type[ENTRY_BUY_ADJUSTMENT]["total_amount"]

    net_profit = (revenue + fees + shipping + buy_costs).quantize(Decimal("0.01"))

    sold_count = fetch_business_sold_count(db, business_id=business_id_norm, start_iso=start_iso, end_iso=end_iso)

    def money(d: Decimal) -> str:
        return str(d.quantize(Decimal("0.01")))

    return {
        "business_id": business_id_norm,
        "start": start_iso,
        "end": end_iso,
        "totals": {
            "revenue": money(revenue),
            "fees": money(fees),
            "shipping_costs": money(shipping),
            "buy_costs": money(buy_costs),
            "net_profit": money(net_profit),
        },
        "counts": {
            "sale_entries": by_type[ENTRY_SALE]["entry_count"],
            "fee_entries": by_type[ENTRY_FEE]["entry_count"],
            "shipping_entries": by_type[ENTRY_SHIPPING_COST]["entry_count"],
            "buy_adjustment_entries": by_type[ENTRY_BUY_ADJUSTMENT]["entry_count"],
            "sold_count": int(sold_count),
        },
    }


# ---------------------------------------------------------------------------
# Read APIs (existing)
# ---------------------------------------------------------------------------

def get_item_ledger(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    entries = fetch_item_ledger_entries(db, business_id=business_id, item_id=item_id, limit=limit, offset=offset)
    totals = fetch_item_ledger_totals(db, business_id=business_id, item_id=item_id)
    return {"business_id": business_id, "item_id": item_id, "entries": entries, "totals": totals}