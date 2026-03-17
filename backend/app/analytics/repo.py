from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, TypedDict

from sqlalchemy import text
from sqlalchemy.orm import Session


class SellThroughCountsRow(TypedDict):
    items_sold: int
    items_created: int


class TimeToSellRowDB(TypedDict):
    item_id: str
    title: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime]
    active_at: Optional[datetime]
    sold_at: Optional[datetime]
    days_to_sell: int


class PriceDropRecommendationRowDB(TypedDict):
    item_id: str
    title: Optional[str]
    status: Optional[str]
    suggested_price: Optional[Decimal]
    min_price: Optional[Decimal]
    market_price: Optional[Decimal]
    age_days: int


class MarketplaceAnalyticsRowDB(TypedDict):
    marketplace: str
    items_sold: int
    gross_sales: Decimal
    net_profit: Decimal
    avg_profit_per_sale: Decimal
    avg_days_to_sell: Decimal


class InventoryHealthRowDB(TypedDict):
    total_active_inventory: int
    fresh_count: int
    aging_count: int
    slow_mover_count: int
    dead_stock_count: int


class InventoryHealthItemRowDB(TypedDict):
    item_id: str
    title: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime]
    active_at: Optional[datetime]
    age_days: int


class PricingOpportunityRowDB(TypedDict):
    item_id: str
    title: Optional[str]
    status: Optional[str]
    market_price: Optional[Decimal]
    suggested_price: Optional[Decimal]
    age_days: int


def fetch_sell_through_counts(
    db: Session,
    *,
    business_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> SellThroughCountsRow:
    sold_sql = """
    SELECT COUNT(*)::int AS items_sold
    FROM items
    WHERE business_id = :business_id
      AND status <> 'Deleted'
      AND sold_at IS NOT NULL
      AND (:start_dt IS NULL OR sold_at >= :start_dt)
      AND (:end_dt   IS NULL OR sold_at <  :end_dt);
    """

    created_sql = """
    SELECT COUNT(*)::int AS items_created
    FROM items
    WHERE business_id = :business_id
      AND status <> 'Deleted'
      AND created_at IS NOT NULL
      AND (:start_dt IS NULL OR created_at >= :start_dt)
      AND (:end_dt   IS NULL OR created_at <  :end_dt);
    """

    sold_row = (
        db.execute(
            text(sold_sql),
            {
                "business_id": business_id,
                "start_dt": start_dt,
                "end_dt": end_dt,
            },
        )
        .mappings()
        .one()
    )

    created_row = (
        db.execute(
            text(created_sql),
            {
                "business_id": business_id,
                "start_dt": start_dt,
                "end_dt": end_dt,
            },
        )
        .mappings()
        .one()
    )

    return {
        "items_sold": int(sold_row["items_sold"] or 0),
        "items_created": int(created_row["items_created"] or 0),
    }


def fetch_time_to_sell_rows(
    db: Session,
    *,
    business_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    limit: int,
    offset: int,
) -> List[TimeToSellRowDB]:
    sql = """
    SELECT
        i.item_id,
        (to_jsonb(i)->>'title') AS title,
        (to_jsonb(i)->>'status') AS status,
        i.created_at,
        i.active_at,
        i.sold_at,
        GREATEST(
            0,
            FLOOR(
                DATE_PART(
                    'day',
                    i.sold_at - COALESCE(i.active_at, i.created_at)
                )
            )
        )::int AS days_to_sell
    FROM items i
    WHERE i.business_id = :business_id
      AND i.status <> 'Deleted'
      AND i.sold_at IS NOT NULL
      AND COALESCE(i.active_at, i.created_at) IS NOT NULL
      AND (:start_dt IS NULL OR i.sold_at >= :start_dt)
      AND (:end_dt   IS NULL OR i.sold_at <  :end_dt)
    ORDER BY i.sold_at DESC, i.item_id DESC
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

    out: List[TimeToSellRowDB] = []
    for r in rows:
        out.append(
            {
                "item_id": str(r["item_id"]),
                "title": r.get("title"),
                "status": r.get("status"),
                "created_at": r.get("created_at"),
                "active_at": r.get("active_at"),
                "sold_at": r.get("sold_at"),
                "days_to_sell": int(r.get("days_to_sell") or 0),
            }
        )
    return out


def fetch_marketplace_analytics_rows(
    db: Session,
    *,
    business_id: str,
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> List[MarketplaceAnalyticsRowDB]:
    sql = """
    WITH sold_item_profit AS (
      SELECT
        le.item_id,
        COALESCE(SUM(CASE WHEN le.entry_type = 'SALE' THEN le.amount ELSE 0 END), 0) AS gross_sales,
        COALESCE(SUM(le.amount), 0) AS net_profit,
        COALESCE(
          NULLIF(BTRIM(s.marketplace), ''),
          NULLIF(BTRIM(l.platform), ''),
          NULLIF(NULLIF(UPPER(BTRIM(le.source)), ''), 'SYSTEM'),
          NULLIF(BTRIM(bs.main_marketplace), ''),
          'Unknown'
        ) AS marketplace
      FROM ledger_entries le
      LEFT JOIN sales s
        ON s.business_id = le.business_id
       AND s.item_id = le.item_id
      LEFT JOIN listings l
        ON l.listing_id = s.listing_id
      LEFT JOIN business_settings bs
        ON bs.business_id = le.business_id
      WHERE le.business_id = :business_id
        AND le.item_id IS NOT NULL
        AND (:start_dt IS NULL OR le.created_at >= :start_dt)
        AND (:end_dt   IS NULL OR le.created_at <  :end_dt)
      GROUP BY
        le.item_id,
        COALESCE(
          NULLIF(BTRIM(s.marketplace), ''),
          NULLIF(BTRIM(l.platform), ''),
          NULLIF(NULLIF(UPPER(BTRIM(le.source)), ''), 'SYSTEM'),
          NULLIF(BTRIM(bs.main_marketplace), ''),
          'Unknown'
        )
    ),
    sold_item_lifecycle AS (
      SELECT
        i.item_id,
        GREATEST(
          0,
          FLOOR(
            DATE_PART(
              'day',
              i.sold_at - COALESCE(i.active_at, i.created_at)
            )
          )
        )::numeric AS days_to_sell
      FROM items i
      WHERE i.business_id = :business_id
        AND i.status <> 'Deleted'
        AND i.sold_at IS NOT NULL
        AND COALESCE(i.active_at, i.created_at) IS NOT NULL
        AND (:start_dt IS NULL OR i.sold_at >= :start_dt)
        AND (:end_dt   IS NULL OR i.sold_at <  :end_dt)
    )
    SELECT
      p.marketplace,
      COUNT(*)::int AS items_sold,
      COALESCE(SUM(p.gross_sales), 0) AS gross_sales,
      COALESCE(SUM(p.net_profit), 0) AS net_profit,
      COALESCE(AVG(p.net_profit), 0) AS avg_profit_per_sale,
      COALESCE(AVG(l.days_to_sell), 0) AS avg_days_to_sell
    FROM sold_item_profit p
    INNER JOIN sold_item_lifecycle l
      ON l.item_id = p.item_id
    WHERE p.gross_sales > 0
    GROUP BY p.marketplace
    ORDER BY net_profit DESC, items_sold DESC, p.marketplace ASC;
    """

    rows = (
        db.execute(
            text(sql),
            {
                "business_id": business_id,
                "start_dt": start_dt,
                "end_dt": end_dt,
            },
        )
        .mappings()
        .all()
    )

    out: List[MarketplaceAnalyticsRowDB] = []
    for r in rows:
        out.append(
            {
                "marketplace": str(r["marketplace"] or "Unknown"),
                "items_sold": int(r["items_sold"] or 0),
                "gross_sales": r["gross_sales"] or Decimal("0"),
                "net_profit": r["net_profit"] or Decimal("0"),
                "avg_profit_per_sale": r["avg_profit_per_sale"] or Decimal("0"),
                "avg_days_to_sell": r["avg_days_to_sell"] or Decimal("0"),
            }
        )
    return out


def fetch_inventory_health_counts(
    db: Session,
    *,
    business_id: str,
) -> InventoryHealthRowDB:
    sql = """
    SELECT
      COUNT(*)::int AS total_active_inventory,

      COALESCE(SUM(
        CASE
          WHEN GREATEST(
            0,
            FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
          )::int < 30
          THEN 1 ELSE 0
        END
      ), 0)::int AS fresh_count,

      COALESCE(SUM(
        CASE
          WHEN GREATEST(
            0,
            FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
          )::int BETWEEN 30 AND 59
          THEN 1 ELSE 0
        END
      ), 0)::int AS aging_count,

      COALESCE(SUM(
        CASE
          WHEN GREATEST(
            0,
            FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
          )::int BETWEEN 60 AND 89
          THEN 1 ELSE 0
        END
      ), 0)::int AS slow_mover_count,

      COALESCE(SUM(
        CASE
          WHEN GREATEST(
            0,
            FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
          )::int >= 90
          THEN 1 ELSE 0
        END
      ), 0)::int AS dead_stock_count
    FROM items i
    WHERE i.business_id = :business_id
      AND COALESCE(i.status, '') NOT IN ('Sold', 'Deleted', 'Archived');
    """

    row = (
        db.execute(
            text(sql),
            {"business_id": business_id},
        )
        .mappings()
        .one()
    )

    return {
        "total_active_inventory": int(row["total_active_inventory"] or 0),
        "fresh_count": int(row["fresh_count"] or 0),
        "aging_count": int(row["aging_count"] or 0),
        "slow_mover_count": int(row["slow_mover_count"] or 0),
        "dead_stock_count": int(row["dead_stock_count"] or 0),
    }


def fetch_inventory_health_items(
    db: Session,
    *,
    business_id: str,
    bucket: str,
    limit: int,
    offset: int,
) -> List[InventoryHealthItemRowDB]:
    bucket = (bucket or "").strip().lower()

    if bucket == "fresh":
        bucket_sql = """
        GREATEST(
          0,
          FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
        )::int < 30
        """
    elif bucket == "aging":
        bucket_sql = """
        GREATEST(
          0,
          FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
        )::int BETWEEN 30 AND 59
        """
    elif bucket == "slow_mover":
        bucket_sql = """
        GREATEST(
          0,
          FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
        )::int BETWEEN 60 AND 89
        """
    elif bucket == "dead_stock":
        bucket_sql = """
        GREATEST(
          0,
          FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
        )::int >= 90
        """
    else:
        raise ValueError("Invalid bucket")

    sql = f"""
    SELECT
      i.item_id,
      (to_jsonb(i)->>'title') AS title,
      (to_jsonb(i)->>'status') AS status,
      i.created_at,
      i.active_at,
      GREATEST(
        0,
        FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
      )::int AS age_days
    FROM items i
    WHERE i.business_id = :business_id
      AND COALESCE(i.status, '') NOT IN ('Sold', 'Deleted', 'Archived')
      AND {bucket_sql}
    ORDER BY age_days DESC, i.created_at ASC NULLS LAST, i.item_id ASC
    LIMIT :limit OFFSET :offset;
    """

    rows = (
        db.execute(
            text(sql),
            {
                "business_id": business_id,
                "limit": limit,
                "offset": offset,
            },
        )
        .mappings()
        .all()
    )

    out: List[InventoryHealthItemRowDB] = []
    for r in rows:
        out.append(
            {
                "item_id": str(r["item_id"]),
                "title": r.get("title"),
                "status": r.get("status"),
                "created_at": r.get("created_at"),
                "active_at": r.get("active_at"),
                "age_days": int(r.get("age_days") or 0),
            }
        )
    return out


def fetch_item_for_repricing_simulation(
    db: Session,
    *,
    business_id: str,
    item_id: str,
):
    """
    Fetch item data needed for repricing simulation.

    Important:
    Some pricing-related fields may not exist as physical DB columns
    in your items table. So we safely read them through to_jsonb(i)->>'field'
    and cast them to numeric when present.
    """

    sql = text(
        """
        SELECT
            i.item_id,
            i.business_id,
            (to_jsonb(i)->>'title') AS title,
            (to_jsonb(i)->>'status') AS status,

            i.suggested_price,
            i.min_price,
            i.market_price,
            i.buy_cost,

            CAST(NULLIF(to_jsonb(i)->>'shipping_cost', '') AS numeric) AS shipping_cost,
            CAST(NULLIF(to_jsonb(i)->>'packaging_cost', '') AS numeric) AS packaging_cost,
            CAST(NULLIF(to_jsonb(i)->>'platform_fee_percent', '') AS numeric) AS platform_fee_percent,
            CAST(NULLIF(to_jsonb(i)->>'promo_fee_percent', '') AS numeric) AS promo_fee_percent

        FROM items i
        WHERE i.item_id = :item_id
          AND i.business_id = :business_id
        LIMIT 1
        """
    )

    return (
        db.execute(
            sql,
            {
                "item_id": item_id,
                "business_id": business_id,
            },
        )
        .mappings()
        .first()
    )

def fetch_items_for_bulk_repricing_simulation(
    db: Session,
    *,
    business_id: str,
    limit: int,
    offset: int,
):
    """
    Fetch many eligible items for bulk repricing simulation.
    Read-only only.
    """

    sql = text(
        """
        SELECT
            i.item_id,
            i.business_id,
            (to_jsonb(i)->>'title') AS title,
            (to_jsonb(i)->>'status') AS status,

            i.suggested_price,
            i.min_price,
            i.market_price,
            i.buy_cost,

            CAST(NULLIF(to_jsonb(i)->>'shipping_cost', '') AS numeric) AS shipping_cost,
            CAST(NULLIF(to_jsonb(i)->>'packaging_cost', '') AS numeric) AS packaging_cost,
            CAST(NULLIF(to_jsonb(i)->>'platform_fee_percent', '') AS numeric) AS platform_fee_percent,
            CAST(NULLIF(to_jsonb(i)->>'promo_fee_percent', '') AS numeric) AS promo_fee_percent

        FROM items i
        WHERE i.business_id = :business_id
          AND COALESCE((to_jsonb(i)->>'status'), '') IN ('Draft', 'Active', 'Archived')
          AND i.suggested_price IS NOT NULL
        ORDER BY i.created_at DESC NULLS LAST, i.item_id DESC
        LIMIT :limit OFFSET :offset
        """
    )

    return (
        db.execute(
            sql,
            {
                "business_id": business_id,
                "limit": limit,
                "offset": offset,
            },
        )
        .mappings()
        .all()
    )

def fetch_pricing_opportunities(
    db: Session,
    *,
    business_id: str,
    signal: str,
    limit: int,
    offset: int,
) -> List[PricingOpportunityRowDB]:
    signal = (signal or "").strip().lower()

    if signal == "underpriced":
        condition = """
        i.market_price IS NOT NULL
        AND i.suggested_price IS NOT NULL
        AND i.suggested_price <= i.market_price * 0.90
        """
    elif signal == "overpriced":
        condition = """
        i.market_price IS NOT NULL
        AND i.suggested_price IS NOT NULL
        AND i.suggested_price >= i.market_price * 1.10
        """
    elif signal == "stale_needs_review":
        condition = """
        GREATEST(
            0,
            FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
        )::int >= 30
        """
    else:
        raise ValueError("Invalid pricing signal")

    sql = f"""
    SELECT
        i.item_id,
        (to_jsonb(i)->>'title') AS title,
        (to_jsonb(i)->>'status') AS status,
        i.market_price,
        i.suggested_price,
        GREATEST(
            0,
            FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
        )::int AS age_days
    FROM items i
    WHERE i.business_id = :business_id
      AND COALESCE(i.status, '') NOT IN ('Sold', 'Deleted', 'Archived')
      AND {condition}
    ORDER BY age_days DESC, i.created_at ASC NULLS LAST, i.item_id ASC
    LIMIT :limit OFFSET :offset
    """

    rows = (
        db.execute(
            text(sql),
            {
                "business_id": business_id,
                "limit": limit,
                "offset": offset,
            },
        )
        .mappings()
        .all()
    )

    out: List[PricingOpportunityRowDB] = []
    for r in rows:
        out.append(
            {
                "item_id": str(r["item_id"]),
                "title": r.get("title"),
                "status": r.get("status"),
                "market_price": r.get("market_price"),
                "suggested_price": r.get("suggested_price"),
                "age_days": int(r.get("age_days") or 0),
            }
        )

    return out


def fetch_price_drop_candidates(
    db: Session,
    *,
    business_id: str,
    limit: int,
    offset: int,
) -> List[PriceDropRecommendationRowDB]:
    sql = """
    SELECT
        i.item_id,
        (to_jsonb(i)->>'title') AS title,
        (to_jsonb(i)->>'status') AS status,
        i.suggested_price,
        i.min_price,
        i.market_price,
        GREATEST(
            0,
            FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
        )::int AS age_days
    FROM items i
    WHERE i.business_id = :business_id
      AND COALESCE(i.status, '') NOT IN ('Sold', 'Deleted', 'Archived')
      AND i.suggested_price IS NOT NULL
      AND i.min_price IS NOT NULL
      AND GREATEST(
            0,
            FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
          )::int >= 30
    ORDER BY age_days DESC, i.created_at ASC NULLS LAST, i.item_id ASC
    LIMIT :limit OFFSET :offset
    """

    rows = (
        db.execute(
            text(sql),
            {
                "business_id": business_id,
                "limit": limit,
                "offset": offset,
            },
        )
        .mappings()
        .all()
    )

    out: List[PriceDropRecommendationRowDB] = []
    for r in rows:
        out.append(
            {
                "item_id": str(r["item_id"]),
                "title": r.get("title"),
                "status": r.get("status"),
                "suggested_price": r.get("suggested_price"),
                "min_price": r.get("min_price"),
                "market_price": r.get("market_price"),
                "age_days": int(r.get("age_days") or 0),
            }
        )
    return out

def fetch_items_for_repricing_strategy(
    db: Session,
    *,
    business_id: str,
    limit: int,
    offset: int,
):

    sql = text(
        """
        SELECT
            i.item_id,
            (to_jsonb(i)->>'title') AS title,
            (to_jsonb(i)->>'status') AS status,

            i.suggested_price,
            i.min_price,
            i.market_price,
            i.buy_cost,

            CAST(NULLIF(to_jsonb(i)->>'shipping_cost','') AS numeric) AS shipping_cost,
            CAST(NULLIF(to_jsonb(i)->>'packaging_cost','') AS numeric) AS packaging_cost,
            CAST(NULLIF(to_jsonb(i)->>'platform_fee_percent','') AS numeric) AS platform_fee_percent,
            CAST(NULLIF(to_jsonb(i)->>'promo_fee_percent','') AS numeric) AS promo_fee_percent,

            GREATEST(
                0,
                FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
            )::int AS age_days

        FROM items i
        WHERE i.business_id = :business_id
          AND COALESCE(i.status,'') NOT IN ('Sold','Deleted')
          AND i.suggested_price IS NOT NULL

        ORDER BY age_days DESC

        LIMIT :limit OFFSET :offset
        """
    )

    return (
        db.execute(
            sql,
            {
                "business_id": business_id,
                "limit": limit,
                "offset": offset,
            },
        )
        .mappings()
        .all()
    )

def fetch_items_for_relist_analysis(
    db: Session,
    *,
    business_id: str,
    limit: int = 200,
):

    sql = text(
        """
        SELECT

            i.item_id,
            (to_jsonb(i)->>'title') AS title,
            (to_jsonb(i)->>'status') AS status,

            i.suggested_price,
            i.market_price,

            GREATEST(
                0,
                FLOOR(DATE_PART('day', NOW() - COALESCE(i.active_at, i.created_at)))
            )::int AS age_days

        FROM items i

        WHERE i.business_id = :business_id
          AND COALESCE(i.status,'') NOT IN ('Sold','Deleted')

        ORDER BY age_days DESC

        LIMIT :limit
        """
    )

    return (
        db.execute(
            sql,
            {
                "business_id": business_id,
                "limit": limit,
            },
        )
        .mappings()
        .all()
    )