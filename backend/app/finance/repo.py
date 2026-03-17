from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session


class ProfitSummaryRow(TypedDict):
    gross_sales: Decimal
    fees: Decimal
    shipping_costs: Decimal
    buy_cost_total: Decimal
    net_profit: Decimal
    sold_count: int


class ProfitTimeseriesRow(TypedDict):
    bucket_start: datetime
    gross_sales: Decimal
    fees: Decimal
    shipping_costs: Decimal
    buy_cost_total: Decimal
    net_profit: Decimal
    sold_count: int


def fetch_profit_summary(
    db: Session,
    *,
    business_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> ProfitSummaryRow:
    sql = """
    SELECT
        COALESCE(SUM(CASE WHEN entry_type = 'SALE' THEN amount ELSE 0 END), 0)                 AS gross_sales,
        COALESCE(SUM(CASE WHEN entry_type = 'FEE' THEN amount ELSE 0 END), 0)                  AS fees,
        COALESCE(SUM(CASE WHEN entry_type = 'SHIPPING_COST' THEN amount ELSE 0 END), 0)        AS shipping_costs,
        COALESCE(SUM(CASE WHEN entry_type = 'BUY_ADJUSTMENT' THEN amount ELSE 0 END), 0)       AS buy_cost_total,
        COALESCE(SUM(amount), 0)                                                               AS net_profit,
        COALESCE(COUNT(DISTINCT CASE WHEN entry_type = 'SALE' THEN item_id ELSE NULL END), 0) AS sold_count
    FROM ledger_entries
    WHERE business_id = :business_id
      AND (:start_dt IS NULL OR created_at >= :start_dt)
      AND (:end_dt   IS NULL OR created_at <  :end_dt);
    """

    row = (
        db.execute(
            text(sql),
            {"business_id": business_id, "start_dt": start_dt, "end_dt": end_dt},
        )
        .mappings()
        .one()
    )

    return {
        "gross_sales": row["gross_sales"] or Decimal("0"),
        "fees": row["fees"] or Decimal("0"),
        "shipping_costs": row["shipping_costs"] or Decimal("0"),
        "buy_cost_total": row["buy_cost_total"] or Decimal("0"),
        "net_profit": row["net_profit"] or Decimal("0"),
        "sold_count": int(row["sold_count"] or 0),
    }


def fetch_profit_timeseries(
    db: Session,
    *,
    business_id: str,
    bucket: Literal["day", "week", "month"],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> List[ProfitTimeseriesRow]:
    if bucket not in ("day", "week", "month"):
        raise ValueError("bucket must be one of: day, week, month")

    sql = f"""
    SELECT
        date_trunc('{bucket}', created_at)                                                      AS bucket_start,
        COALESCE(SUM(CASE WHEN entry_type = 'SALE' THEN amount ELSE 0 END), 0)                 AS gross_sales,
        COALESCE(SUM(CASE WHEN entry_type = 'FEE' THEN amount ELSE 0 END), 0)                  AS fees,
        COALESCE(SUM(CASE WHEN entry_type = 'SHIPPING_COST' THEN amount ELSE 0 END), 0)        AS shipping_costs,
        COALESCE(SUM(CASE WHEN entry_type = 'BUY_ADJUSTMENT' THEN amount ELSE 0 END), 0)       AS buy_cost_total,
        COALESCE(SUM(amount), 0)                                                               AS net_profit,
        COALESCE(COUNT(DISTINCT CASE WHEN entry_type = 'SALE' THEN item_id ELSE NULL END), 0) AS sold_count
    FROM ledger_entries
    WHERE business_id = :business_id
      AND (:start_dt IS NULL OR created_at >= :start_dt)
      AND (:end_dt   IS NULL OR created_at <  :end_dt)
    GROUP BY 1
    ORDER BY 1 ASC;
    """

    rows = (
        db.execute(
            text(sql),
            {"business_id": business_id, "start_dt": start_dt, "end_dt": end_dt},
        )
        .mappings()
        .all()
    )

    out: List[ProfitTimeseriesRow] = []
    for r in rows:
        out.append(
            {
                "bucket_start": r["bucket_start"],
                "gross_sales": r["gross_sales"] or Decimal("0"),
                "fees": r["fees"] or Decimal("0"),
                "shipping_costs": r["shipping_costs"] or Decimal("0"),
                "buy_cost_total": r["buy_cost_total"] or Decimal("0"),
                "net_profit": r["net_profit"] or Decimal("0"),
                "sold_count": int(r["sold_count"] or 0),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Per-item profit report (schema-safe join against items)
# ---------------------------------------------------------------------------

class ItemProfitRowDB(TypedDict):
    item_id: str
    sold_at: Optional[datetime]
    title: Optional[str]
    sku: Optional[str]
    brand: Optional[str]
    size: Optional[str]
    status: Optional[str]
    gross_sales: Decimal
    fees: Decimal
    shipping_costs: Decimal
    buy_cost_total: Decimal
    net_profit: Decimal


def fetch_item_profit_report(
    db: Session,
    *,
    business_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    limit: int,
    offset: int,
    order: Literal["profit_desc", "profit_asc", "sold_desc", "sold_asc"],
) -> List[ItemProfitRowDB]:
    order_sql = {
        "profit_desc": "a.net_profit DESC NULLS LAST",
        "profit_asc": "a.net_profit ASC NULLS LAST",
        "sold_desc": "a.sold_at DESC NULLS LAST",
        "sold_asc": "a.sold_at ASC NULLS LAST",
    }[order]

    sql = f"""
    WITH item_agg AS (
      SELECT
        le.item_id,
        MAX(CASE WHEN le.entry_type = 'SALE' THEN le.created_at ELSE NULL END)                  AS sold_at,
        COALESCE(SUM(CASE WHEN le.entry_type = 'SALE' THEN le.amount ELSE 0 END), 0)           AS gross_sales,
        COALESCE(SUM(CASE WHEN le.entry_type = 'FEE' THEN le.amount ELSE 0 END), 0)            AS fees,
        COALESCE(SUM(CASE WHEN le.entry_type = 'SHIPPING_COST' THEN le.amount ELSE 0 END), 0)  AS shipping_costs,
        COALESCE(SUM(CASE WHEN le.entry_type = 'BUY_ADJUSTMENT' THEN le.amount ELSE 0 END), 0) AS buy_cost_total,
        COALESCE(SUM(le.amount), 0)                                                             AS net_profit
      FROM ledger_entries le
      WHERE le.business_id = :business_id
        AND le.item_id IS NOT NULL
        AND (:start_dt IS NULL OR le.created_at >= :start_dt)
        AND (:end_dt   IS NULL OR le.created_at <  :end_dt)
      GROUP BY le.item_id
    )
    SELECT
      a.item_id,
      a.sold_at,

      (to_jsonb(i)->>'title')  AS title,
      (to_jsonb(i)->>'sku')    AS sku,
      (to_jsonb(i)->>'brand')  AS brand,
      (to_jsonb(i)->>'size')   AS size,
      (to_jsonb(i)->>'status') AS status,

      a.gross_sales,
      a.fees,
      a.shipping_costs,
      a.buy_cost_total,
      a.net_profit
    FROM item_agg a
    LEFT JOIN items i
      ON i.item_id = a.item_id
     AND i.business_id = :business_id
    WHERE a.sold_at IS NOT NULL
    ORDER BY {order_sql}
    LIMIT :limit OFFSET :offset;
    """

    rows = (
        db.execute(
            text(sql),
            {
                "business_id": business_id,
                "start_dt": start_dt,
                "end_dt": end_dt,
                "limit": limit,
                "offset": offset,
            },
        )
        .mappings()
        .all()
    )

    out: List[ItemProfitRowDB] = []
    for r in rows:
        out.append(
            {
                "item_id": str(r["item_id"]),
                "sold_at": r["sold_at"],
                "title": r.get("title"),
                "sku": r.get("sku"),
                "brand": r.get("brand"),
                "size": r.get("size"),
                "status": r.get("status"),
                "gross_sales": r["gross_sales"] or Decimal("0"),
                "fees": r["fees"] or Decimal("0"),
                "shipping_costs": r["shipping_costs"] or Decimal("0"),
                "buy_cost_total": r["buy_cost_total"] or Decimal("0"),
                "net_profit": r["net_profit"] or Decimal("0"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Single item profit details
# ---------------------------------------------------------------------------

class ItemProfitSummaryDB(TypedDict):
    item_id: str
    sold_at: Optional[datetime]
    title: Optional[str]
    sku: Optional[str]
    brand: Optional[str]
    size: Optional[str]
    status: Optional[str]
    gross_sales: Decimal
    fees: Decimal
    shipping_costs: Decimal
    buy_cost_total: Decimal
    net_profit: Decimal


class LedgerLineDB(TypedDict):
    entry_type: str
    amount: Decimal
    created_at: datetime


def fetch_item_profit_summary(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> Optional[ItemProfitSummaryDB]:
    sql = """
    WITH item_agg AS (
      SELECT
        le.item_id,
        MAX(CASE WHEN le.entry_type = 'SALE' THEN le.created_at ELSE NULL END)                  AS sold_at,
        COALESCE(SUM(CASE WHEN le.entry_type = 'SALE' THEN le.amount ELSE 0 END), 0)           AS gross_sales,
        COALESCE(SUM(CASE WHEN le.entry_type = 'FEE' THEN le.amount ELSE 0 END), 0)            AS fees,
        COALESCE(SUM(CASE WHEN le.entry_type = 'SHIPPING_COST' THEN le.amount ELSE 0 END), 0)  AS shipping_costs,
        COALESCE(SUM(CASE WHEN le.entry_type = 'BUY_ADJUSTMENT' THEN le.amount ELSE 0 END), 0) AS buy_cost_total,
        COALESCE(SUM(le.amount), 0)                                                             AS net_profit
      FROM ledger_entries le
      WHERE le.business_id = :business_id
        AND le.item_id = :item_id
        AND (:start_dt IS NULL OR le.created_at >= :start_dt)
        AND (:end_dt   IS NULL OR le.created_at <  :end_dt)
      GROUP BY le.item_id
    )
    SELECT
      a.item_id,
      a.sold_at,
      (to_jsonb(i)->>'title')  AS title,
      (to_jsonb(i)->>'sku')    AS sku,
      (to_jsonb(i)->>'brand')  AS brand,
      (to_jsonb(i)->>'size')   AS size,
      (to_jsonb(i)->>'status') AS status,
      a.gross_sales,
      a.fees,
      a.shipping_costs,
      a.buy_cost_total,
      a.net_profit
    FROM item_agg a
    LEFT JOIN items i
      ON i.item_id = a.item_id
     AND i.business_id = :business_id;
    """

    row = (
        db.execute(
            text(sql),
            {
                "business_id": business_id,
                "item_id": item_id,
                "start_dt": start_dt,
                "end_dt": end_dt,
            },
        )
        .mappings()
        .one_or_none()
    )

    if not row:
        return None

    return {
        "item_id": str(row["item_id"]),
        "sold_at": row["sold_at"],
        "title": row.get("title"),
        "sku": row.get("sku"),
        "brand": row.get("brand"),
        "size": row.get("size"),
        "status": row.get("status"),
        "gross_sales": row["gross_sales"] or Decimal("0"),
        "fees": row["fees"] or Decimal("0"),
        "shipping_costs": row["shipping_costs"] or Decimal("0"),
        "buy_cost_total": row["buy_cost_total"] or Decimal("0"),
        "net_profit": row["net_profit"] or Decimal("0"),
    }


def fetch_item_ledger_lines(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> List[LedgerLineDB]:
    sql = """
    SELECT
      entry_type,
      amount,
      created_at
    FROM ledger_entries
    WHERE business_id = :business_id
      AND item_id = :item_id
      AND (:start_dt IS NULL OR created_at >= :start_dt)
      AND (:end_dt   IS NULL OR created_at <  :end_dt)
    ORDER BY created_at ASC;
    """

    rows = (
        db.execute(
            text(sql),
            {
                "business_id": business_id,
                "item_id": item_id,
                "start_dt": start_dt,
                "end_dt": end_dt,
            },
        )
        .mappings()
        .all()
    )

    out: List[LedgerLineDB] = []
    for r in rows:
        out.append(
            {
                "entry_type": str(r["entry_type"]),
                "amount": r["amount"] or Decimal("0"),
                "created_at": r["created_at"],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Top-items ranking / worst-items / low-margin base aggregate
# ---------------------------------------------------------------------------

def fetch_items_profit_aggregate_for_ranking(
    db: Session,
    *,
    business_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> List[Dict[str, Any]]:
    sql = text(
        """
        WITH item_agg AS (
          SELECT
            le.item_id,
            MAX(CASE WHEN le.entry_type = 'SALE' THEN le.created_at ELSE NULL END)                  AS sold_at,
            COALESCE(SUM(CASE WHEN le.entry_type = 'SALE' THEN le.amount ELSE 0 END), 0)           AS gross_sales,
            COALESCE(SUM(CASE WHEN le.entry_type = 'FEE' THEN le.amount ELSE 0 END), 0)            AS fees,
            COALESCE(SUM(CASE WHEN le.entry_type = 'SHIPPING_COST' THEN le.amount ELSE 0 END), 0)  AS shipping_costs,
            COALESCE(SUM(CASE WHEN le.entry_type = 'BUY_ADJUSTMENT' THEN le.amount ELSE 0 END), 0) AS buy_cost_total,
            COALESCE(SUM(le.amount), 0)                                                             AS net_profit
          FROM ledger_entries le
          WHERE le.business_id = :business_id
            AND le.item_id IS NOT NULL
            AND (:start_dt IS NULL OR le.created_at >= :start_dt)
            AND (:end_dt   IS NULL OR le.created_at <  :end_dt)
          GROUP BY le.item_id
        )
        SELECT
          a.item_id,
          a.sold_at,

          (to_jsonb(i)->>'title')  AS title,
          (to_jsonb(i)->>'sku')    AS sku,
          (to_jsonb(i)->>'brand')  AS brand,
          (to_jsonb(i)->>'size')   AS size,
          (to_jsonb(i)->>'status') AS status,

          a.gross_sales,
          a.fees,
          a.shipping_costs,
          a.buy_cost_total,
          a.net_profit
        FROM item_agg a
        LEFT JOIN items i
          ON i.item_id = a.item_id
         AND i.business_id = :business_id
        WHERE a.sold_at IS NOT NULL
        """
    )

    rows = (
        db.execute(
            sql,
            {"business_id": business_id, "start_dt": start_dt, "end_dt": end_dt},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Profit by platform (improved fallbacks)
# ---------------------------------------------------------------------------

class ProfitByPlatformRowDB(TypedDict):
    platform: str
    gross_sales: Decimal
    fees: Decimal
    shipping_costs: Decimal
    buy_cost_total: Decimal
    net_profit: Decimal
    sold_count: int


def fetch_profit_by_platform(
    db: Session,
    *,
    business_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> List[ProfitByPlatformRowDB]:
    """
    Group ledger profit by platform using (most reliable first):

      1) sales.marketplace (if sales row exists)
      2) listings.platform (fallback)
      3) ledger_entries.source (fallback)
         - BUT: we treat 'SYSTEM' as "no platform", so it won't become the platform label
      4) business_settings.main_marketplace (final fallback)
      5) 'Unknown'
    """
    sql = """
    WITH le_scoped AS (
      SELECT *
      FROM ledger_entries
      WHERE business_id = :business_id
        AND item_id IS NOT NULL
        AND (:start_dt IS NULL OR created_at >= :start_dt)
        AND (:end_dt   IS NULL OR created_at <  :end_dt)
    )
    SELECT
      COALESCE(
        NULLIF(BTRIM(s.marketplace), ''),
        NULLIF(BTRIM(l.platform), ''),
        NULLIF(NULLIF(UPPER(BTRIM(le.source)), ''), 'SYSTEM'),
        NULLIF(BTRIM(bs.main_marketplace), ''),
        'Unknown'
      )                                                                                            AS platform,

      COALESCE(SUM(CASE WHEN le.entry_type = 'SALE' THEN le.amount ELSE 0 END), 0)                AS gross_sales,
      COALESCE(SUM(CASE WHEN le.entry_type = 'FEE' THEN le.amount ELSE 0 END), 0)                 AS fees,
      COALESCE(SUM(CASE WHEN le.entry_type = 'SHIPPING_COST' THEN le.amount ELSE 0 END), 0)       AS shipping_costs,
      COALESCE(SUM(CASE WHEN le.entry_type = 'BUY_ADJUSTMENT' THEN le.amount ELSE 0 END), 0)      AS buy_cost_total,
      COALESCE(SUM(le.amount), 0)                                                                  AS net_profit,

      COALESCE(COUNT(DISTINCT CASE WHEN le.entry_type = 'SALE' THEN le.item_id ELSE NULL END), 0) AS sold_count
    FROM le_scoped le
    LEFT JOIN sales s
      ON s.business_id = le.business_id
     AND s.item_id = le.item_id
    LEFT JOIN listings l
      ON l.listing_id = s.listing_id
    LEFT JOIN business_settings bs
      ON bs.business_id = le.business_id
    GROUP BY 1
    ORDER BY net_profit DESC;
    """

    rows = (
        db.execute(
            text(sql),
            {"business_id": business_id, "start_dt": start_dt, "end_dt": end_dt},
        )
        .mappings()
        .all()
    )

    out: List[ProfitByPlatformRowDB] = []
    for r in rows:
        out.append(
            {
                "platform": str(r["platform"] or "Unknown"),
                "gross_sales": r["gross_sales"] or Decimal("0"),
                "fees": r["fees"] or Decimal("0"),
                "shipping_costs": r["shipping_costs"] or Decimal("0"),
                "buy_cost_total": r["buy_cost_total"] or Decimal("0"),
                "net_profit": r["net_profit"] or Decimal("0"),
                "sold_count": int(r["sold_count"] or 0),
            }
        )
    return out