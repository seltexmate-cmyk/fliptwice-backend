from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.analytics.repo import (
    fetch_inventory_health_counts,
    fetch_inventory_health_items,
    fetch_item_for_repricing_simulation,
    fetch_items_for_bulk_repricing_simulation,
    fetch_marketplace_analytics_rows,
    fetch_price_drop_candidates,
    fetch_pricing_opportunities,
    fetch_sell_through_counts,
    fetch_time_to_sell_rows,
    fetch_items_for_repricing_strategy,
    fetch_items_for_relist_analysis,
)
from app.analytics.schemas import (
    BulkRepricingSimulationResponse,
    BulkRepricingSimulationRow,
    InventoryHealthItemRow,
    InventoryHealthItemsResponse,
    InventoryHealthResponse,
    MarketplaceAnalyticsResponse,
    MarketplaceAnalyticsRow,
    PriceDropRecommendationRow,
    PriceDropRecommendationsResponse,
    PricingOpportunityRow,
    PricingOpportunitiesResponse,
    SellThroughResponse,
    TimeToSellResponse,
    TimeToSellRow,
    RepricingStrategyRequest,
    RepricingStrategyResponse,
    RepricingStrategyRow,
    RelistOpportunitiesResponse,
    RelistOpportunityRow,
)

def _parse_yyyy_mm_dd(value: str) -> date:
    return date.fromisoformat(value)


def _q2(value: Optional[Decimal]) -> Decimal:
    return (value or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_money_str(value: Optional[Decimal]) -> str:
    return str(_q2(value))


def _to_optional_money_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return str(_q2(value))


def _to_start_end_datetimes(
    start: Optional[str],
    end: Optional[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None

    if start:
        d = _parse_yyyy_mm_dd(start)
        start_dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

    if end:
        d = _parse_yyyy_mm_dd(end)
        next_day = d + timedelta(days=1)
        end_dt = datetime(next_day.year, next_day.month, next_day.day, tzinfo=timezone.utc)

    return start_dt, end_dt


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _normalize_test_prices(raw_prices: List[object]) -> List[Decimal]:
    normalized: List[Decimal] = []

    for value in raw_prices:
        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip().replace(",", ".")

        try:
            price = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid price value: {value}",
            )

        if price <= 0:
            raise HTTPException(
                status_code=400,
                detail="Price must be positive",
            )

        normalized.append(price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    if not normalized:
        raise HTTPException(
            status_code=400,
            detail="At least one valid test price is required",
        )

    normalized = sorted(set(normalized), reverse=True)
    return normalized


def _safe_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _calculate_projected_profit(
    *,
    sale_price: Decimal,
    buy_cost: Decimal,
    shipping_cost: Decimal,
    packaging_cost: Decimal,
    platform_fee_percent: Decimal,
    promo_fee_percent: Decimal,
) -> Decimal:
    """
    Project profit for a test sale price.

    This does NOT write to the ledger.
    This is simulation only.
    """

    total_fee_percent = platform_fee_percent + promo_fee_percent
    fee_rate = total_fee_percent / Decimal("100")
    fee_amount = sale_price * fee_rate

    profit = sale_price - fee_amount - (buy_cost + shipping_cost + packaging_cost)
    return _q2(profit)


def _determine_risk_level(
    *,
    test_price: Decimal,
    min_price: Optional[Decimal],
    market_price: Optional[Decimal],
    margin_percent: Decimal,
) -> str:
    if min_price is not None and test_price < min_price:
        return "HIGH"

    if margin_percent < Decimal("10"):
        return "HIGH"

    if market_price is not None and test_price > (market_price * Decimal("1.15")):
        return "MEDIUM"

    if margin_percent < Decimal("20"):
        return "MEDIUM"

    return "LOW"


def _determine_reason(
    *,
    test_price: Decimal,
    min_price: Optional[Decimal],
    market_price: Optional[Decimal],
    margin_percent: Decimal,
) -> str:
    if min_price is not None and test_price < min_price:
        return "below_min_price"

    if market_price is not None and test_price > (market_price * Decimal("1.15")):
        return "above_market_range"

    if margin_percent < Decimal("10"):
        return "margin_too_low"

    if min_price is not None and test_price == min_price:
        return "at_floor_price"

    return "healthy_margin_after_drop"


def _risk_rank(risk_level: str) -> int:
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    return order.get(risk_level, 99)


def get_sell_through(
    db: Session,
    *,
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> SellThroughResponse:
    start_dt, end_dt = _to_start_end_datetimes(start, end)

    counts = fetch_sell_through_counts(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    items_sold = int(counts["items_sold"])
    items_created = int(counts["items_created"])

    rate = Decimal("0")
    if items_created > 0:
        rate = (Decimal(items_sold) / Decimal(items_created)) * Decimal("100")

    return SellThroughResponse(
        business_id=business_id,
        start=start,
        end=end,
        items_sold=items_sold,
        items_created=items_created,
        sell_through_rate=_q2(rate),
    )


def get_time_to_sell(
    db: Session,
    *,
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> TimeToSellResponse:
    try:
        limit_i = int(limit)
        offset_i = int(offset)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pagination params: {exc}")

    limit_i = max(1, min(limit_i, 200))
    offset_i = max(0, offset_i)

    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows_db = fetch_time_to_sell_rows(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=limit_i,
        offset=offset_i,
    )

    days_values = [int(r["days_to_sell"]) for r in rows_db]
    items_sold = len(days_values)

    avg_days = Decimal("0")
    median_days = Decimal("0")
    fastest_days: Optional[int] = None
    slowest_days: Optional[int] = None

    if days_values:
        sorted_days = sorted(days_values)
        avg_days = Decimal(sum(sorted_days)) / Decimal(len(sorted_days))
        fastest_days = sorted_days[0]
        slowest_days = sorted_days[-1]

        mid = len(sorted_days) // 2
        if len(sorted_days) % 2 == 1:
            median_days = Decimal(sorted_days[mid])
        else:
            median_days = (Decimal(sorted_days[mid - 1]) + Decimal(sorted_days[mid])) / Decimal("2")

    rows: List[TimeToSellRow] = []
    for r in rows_db:
        rows.append(
            TimeToSellRow(
                item_id=str(r["item_id"]),
                title=r.get("title"),
                status=r.get("status"),
                created_at=_iso_utc(r.get("created_at")),
                active_at=_iso_utc(r.get("active_at")),
                sold_at=_iso_utc(r.get("sold_at")),
                days_to_sell=int(r["days_to_sell"]),
            )
        )

    return TimeToSellResponse(
        business_id=business_id,
        start=start,
        end=end,
        items_sold=items_sold,
        avg_days_to_sell=_q2(avg_days),
        median_days_to_sell=_q2(median_days),
        fastest_sale_days=fastest_days,
        slowest_sale_days=slowest_days,
        rows=rows,
    )


def get_marketplace_analytics(
    db: Session,
    *,
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> MarketplaceAnalyticsResponse:
    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows_db = fetch_marketplace_analytics_rows(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    rows: List[MarketplaceAnalyticsRow] = []
    for r in rows_db:
        rows.append(
            MarketplaceAnalyticsRow(
                marketplace=str(r["marketplace"]),
                items_sold=int(r["items_sold"]),
                gross_sales=_q2(Decimal(r["gross_sales"])),
                net_profit=_q2(Decimal(r["net_profit"])),
                avg_profit_per_sale=_q2(Decimal(r["avg_profit_per_sale"])),
                avg_days_to_sell=_q2(Decimal(r["avg_days_to_sell"])),
            )
        )

    return MarketplaceAnalyticsResponse(
        business_id=business_id,
        start=start,
        end=end,
        rows=rows,
    )


def get_inventory_health(
    db: Session,
    *,
    business_id: str,
) -> InventoryHealthResponse:
    counts = fetch_inventory_health_counts(
        db,
        business_id=business_id,
    )

    total_active_inventory = int(counts["total_active_inventory"])
    fresh_count = int(counts["fresh_count"])
    aging_count = int(counts["aging_count"])
    slow_mover_count = int(counts["slow_mover_count"])
    dead_stock_count = int(counts["dead_stock_count"])

    dead_stock_ratio = Decimal("0")
    if total_active_inventory > 0:
        dead_stock_ratio = (
            Decimal(dead_stock_count) / Decimal(total_active_inventory)
        ) * Decimal("100")

    return InventoryHealthResponse(
        business_id=business_id,
        as_of=datetime.now(timezone.utc).isoformat(),
        total_active_inventory=total_active_inventory,
        fresh_count=fresh_count,
        aging_count=aging_count,
        slow_mover_count=slow_mover_count,
        dead_stock_count=dead_stock_count,
        dead_stock_ratio=_q2(dead_stock_ratio),
    )


def get_inventory_health_items(
    db: Session,
    *,
    business_id: str,
    bucket: str,
    limit: int = 50,
    offset: int = 0,
) -> InventoryHealthItemsResponse:
    try:
        limit_i = int(limit)
        offset_i = int(offset)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pagination params: {exc}")

    limit_i = max(1, min(limit_i, 200))
    offset_i = max(0, offset_i)

    bucket_norm = (bucket or "").strip().lower()
    allowed = {"fresh", "aging", "slow_mover", "dead_stock"}
    if bucket_norm not in allowed:
        raise HTTPException(
            status_code=400,
            detail="bucket must be one of: fresh, aging, slow_mover, dead_stock",
        )

    try:
        rows_db = fetch_inventory_health_items(
            db,
            business_id=business_id,
            bucket=bucket_norm,
            limit=limit_i,
            offset=offset_i,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    rows: List[InventoryHealthItemRow] = []
    for r in rows_db:
        rows.append(
            InventoryHealthItemRow(
                item_id=str(r["item_id"]),
                title=r.get("title"),
                status=r.get("status"),
                created_at=_iso_utc(r.get("created_at")),
                active_at=_iso_utc(r.get("active_at")),
                age_days=int(r["age_days"]),
            )
        )

    return InventoryHealthItemsResponse(
        business_id=business_id,
        bucket=bucket_norm,
        limit=limit_i,
        offset=offset_i,
        rows=rows,
    )


def get_pricing_opportunities(
    db: Session,
    *,
    business_id: str,
    signal: str,
    limit: int = 50,
    offset: int = 0,
) -> PricingOpportunitiesResponse:
    try:
        rows_db = fetch_pricing_opportunities(
            db,
            business_id=business_id,
            signal=signal,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    rows: List[PricingOpportunityRow] = []
    for r in rows_db:
        rows.append(
            PricingOpportunityRow(
                item_id=str(r["item_id"]),
                title=r.get("title"),
                status=r.get("status"),
                market_price=r.get("market_price"),
                suggested_price=r.get("suggested_price"),
                age_days=int(r["age_days"]),
                pricing_signal=signal,
            )
        )

    return PricingOpportunitiesResponse(
        business_id=business_id,
        signal=signal,
        limit=limit,
        offset=offset,
        rows=rows,
    )


def get_price_drop_recommendations(
    db: Session,
    *,
    business_id: str,
    limit: int = 50,
    offset: int = 0,
) -> PriceDropRecommendationsResponse:
    try:
        limit_i = int(limit)
        offset_i = int(offset)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pagination params: {exc}")

    limit_i = max(1, min(limit_i, 200))
    offset_i = max(0, offset_i)

    rows_db = fetch_price_drop_candidates(
        db,
        business_id=business_id,
        limit=limit_i,
        offset=offset_i,
    )

    rows: List[PriceDropRecommendationRow] = []

    for r in rows_db:
        age_days = int(r["age_days"])
        current_price = Decimal(r["suggested_price"]) if r.get("suggested_price") is not None else None
        min_price = Decimal(r["min_price"]) if r.get("min_price") is not None else None
        market_price = Decimal(r["market_price"]) if r.get("market_price") is not None else None

        if current_price is None or min_price is None:
            continue

        if age_days >= 90:
            drop_percent = Decimal("15.00")
            reason = "slow_mover_90_plus_days"
        elif age_days >= 60:
            drop_percent = Decimal("10.00")
            reason = "slow_mover_60_plus_days"
        else:
            drop_percent = Decimal("5.00")
            reason = "slow_mover_30_plus_days"

        discounted_price = current_price * (Decimal("1.00") - (drop_percent / Decimal("100")))
        recommended_price = discounted_price

        if recommended_price < min_price:
            recommended_price = min_price

        if market_price is not None and recommended_price > market_price:
            recommended_price = market_price if market_price >= min_price else min_price

        rows.append(
            PriceDropRecommendationRow(
                item_id=str(r["item_id"]),
                title=r.get("title"),
                status=r.get("status"),
                age_days=age_days,
                current_price=_q2(current_price),
                min_price=_q2(min_price),
                market_price=_q2(market_price) if market_price is not None else None,
                recommended_price=_q2(recommended_price),
                drop_percent=_q2(drop_percent),
                reason=reason,
            )
        )

    return PriceDropRecommendationsResponse(
        business_id=business_id,
        limit=limit_i,
        offset=offset_i,
        rows=rows,
    )


def simulate_repricing(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    raw_test_prices: List[object],
):
    row = fetch_item_for_repricing_simulation(
        db,
        business_id=business_id,
        item_id=item_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    status = str(row.get("status") or "")
    if status in {"Sold", "Deleted"}:
        raise HTTPException(
            status_code=400,
            detail=f"Repricing simulation is not allowed for {status} items",
        )

    if row.get("suggested_price") is None:
        raise HTTPException(
            status_code=400,
            detail="Suggested price is required for repricing simulation",
        )

    test_prices = _normalize_test_prices(raw_test_prices)

    current_price = Decimal(str(row["suggested_price"]))
    min_price = Decimal(str(row["min_price"])) if row.get("min_price") is not None else None
    market_price = Decimal(str(row["market_price"])) if row.get("market_price") is not None else None

    buy_cost = _safe_decimal(row.get("buy_cost"))
    shipping_cost = _safe_decimal(row.get("shipping_cost"))
    packaging_cost = _safe_decimal(row.get("packaging_cost"))
    platform_fee_percent = _safe_decimal(row.get("platform_fee_percent"))
    promo_fee_percent = _safe_decimal(row.get("promo_fee_percent"))

    current_profit = _calculate_projected_profit(
        sale_price=current_price,
        buy_cost=buy_cost,
        shipping_cost=shipping_cost,
        packaging_cost=packaging_cost,
        platform_fee_percent=platform_fee_percent,
        promo_fee_percent=promo_fee_percent,
    )

    current_margin_percent = Decimal("0")
    if current_price > 0:
        current_margin_percent = (current_profit / current_price) * Decimal("100")

    simulations = []

    for price in test_prices:
        profit_after = _calculate_projected_profit(
            sale_price=price,
            buy_cost=buy_cost,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
            platform_fee_percent=platform_fee_percent,
            promo_fee_percent=promo_fee_percent,
        )

        margin_after_percent = Decimal("0")
        if price > 0:
            margin_after_percent = (profit_after / price) * Decimal("100")

        profit_change = profit_after - current_profit
        margin_change_percent = margin_after_percent - current_margin_percent

        min_price_guard_triggered = bool(min_price is not None and price < min_price)
        market_price_guard_triggered = bool(
            market_price is not None and price > (market_price * Decimal("1.15"))
        )

        risk_level = _determine_risk_level(
            test_price=price,
            min_price=min_price,
            market_price=market_price,
            margin_percent=margin_after_percent,
        )

        recommendation_reason = _determine_reason(
            test_price=price,
            min_price=min_price,
            market_price=market_price,
            margin_percent=margin_after_percent,
        )

        simulations.append(
            {
                "test_price": _to_money_str(price),
                "profit_after": _to_money_str(profit_after),
                "margin_after_percent": _to_money_str(margin_after_percent),
                "profit_change": _to_money_str(profit_change),
                "margin_change_percent": _to_money_str(margin_change_percent),
                "min_price_guard_triggered": min_price_guard_triggered,
                "market_price_guard_triggered": market_price_guard_triggered,
                "risk_level": risk_level,
                "recommendation_reason": recommendation_reason,
            }
        )

    valid_for_profit = [
        s for s in simulations if not s["min_price_guard_triggered"]
    ]
    if not valid_for_profit:
        valid_for_profit = simulations

    best_profit = max(valid_for_profit, key=lambda x: Decimal(x["profit_after"]))
    lowest_risk = min(
        simulations,
        key=lambda x: (_risk_rank(x["risk_level"]), -Decimal(x["profit_after"])),
    )

    safe_candidates = [
        s
        for s in simulations
        if s["risk_level"] == "LOW"
        and not s["min_price_guard_triggered"]
        and not s["market_price_guard_triggered"]
    ]

    if safe_candidates:
        recommended = max(safe_candidates, key=lambda x: Decimal(x["profit_after"]))
    else:
        medium_candidates = [
            s for s in simulations if s["risk_level"] == "MEDIUM" and not s["min_price_guard_triggered"]
        ]
        if medium_candidates:
            recommended = max(medium_candidates, key=lambda x: Decimal(x["profit_after"]))
        else:
            recommended = lowest_risk

    return {
        "item_id": str(row["item_id"]),
        "title": row.get("title"),
        "currency": "EUR",
        "status": status,
        "current_price": _to_money_str(current_price),
        "current_profit": _to_money_str(current_profit),
        "current_margin_percent": _to_money_str(current_margin_percent),
        "min_price": _to_optional_money_str(min_price),
        "market_price": _to_optional_money_str(market_price),
        "recommended_price": recommended["test_price"],
        "recommended_strategy": "best_balance_profit_and_competitiveness",
        "best_profit_price": best_profit["test_price"],
        "lowest_risk_price": lowest_risk["test_price"],
        "simulations": simulations,
    }

def _normalize_drop_percent(raw_value: object) -> Decimal:
    if raw_value is None:
        raise HTTPException(status_code=400, detail="price_drop_percent is required")

    if isinstance(raw_value, str):
        raw_value = raw_value.strip().replace(",", ".")

    try:
        value = Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid price_drop_percent: {raw_value}")

    if value <= 0:
        raise HTTPException(status_code=400, detail="price_drop_percent must be positive")

    if value >= Decimal("100"):
        raise HTTPException(status_code=400, detail="price_drop_percent must be less than 100")

    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def simulate_bulk_repricing(
    db: Session,
    *,
    business_id: str,
    price_drop_percent: object,
    limit: int = 50,
    offset: int = 0,
) -> BulkRepricingSimulationResponse:
    drop_percent = _normalize_drop_percent(price_drop_percent)

    try:
        limit_i = int(limit)
        offset_i = int(offset)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pagination params: {exc}")

    limit_i = max(1, min(limit_i, 200))
    offset_i = max(0, offset_i)

    rows_db = fetch_items_for_bulk_repricing_simulation(
        db,
        business_id=business_id,
        limit=limit_i,
        offset=offset_i,
    )

    result_rows: List[BulkRepricingSimulationRow] = []

    total_current_profit = Decimal("0")
    total_projected_profit = Decimal("0")

    safe_items = 0
    risky_items = 0
    high_risk_items = 0

    drop_multiplier = Decimal("1.00") - (drop_percent / Decimal("100"))

    for row in rows_db:
        current_price = Decimal(str(row["suggested_price"]))
        test_price = (current_price * drop_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        min_price = Decimal(str(row["min_price"])) if row.get("min_price") is not None else None
        market_price = Decimal(str(row["market_price"])) if row.get("market_price") is not None else None

        buy_cost = _safe_decimal(row.get("buy_cost"))
        shipping_cost = _safe_decimal(row.get("shipping_cost"))
        packaging_cost = _safe_decimal(row.get("packaging_cost"))
        platform_fee_percent = _safe_decimal(row.get("platform_fee_percent"))
        promo_fee_percent = _safe_decimal(row.get("promo_fee_percent"))

        current_profit = _calculate_projected_profit(
            sale_price=current_price,
            buy_cost=buy_cost,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
            platform_fee_percent=platform_fee_percent,
            promo_fee_percent=promo_fee_percent,
        )

        projected_profit = _calculate_projected_profit(
            sale_price=test_price,
            buy_cost=buy_cost,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
            platform_fee_percent=platform_fee_percent,
            promo_fee_percent=promo_fee_percent,
        )

        profit_change = projected_profit - current_profit

        margin_after_percent = Decimal("0")
        if test_price > 0:
            margin_after_percent = (projected_profit / test_price) * Decimal("100")

        min_price_guard_triggered = bool(min_price is not None and test_price < min_price)
        market_price_guard_triggered = bool(
            market_price is not None and test_price > (market_price * Decimal("1.15"))
        )

        risk_level = _determine_risk_level(
            test_price=test_price,
            min_price=min_price,
            market_price=market_price,
            margin_percent=margin_after_percent,
        )

        recommendation_reason = _determine_reason(
            test_price=test_price,
            min_price=min_price,
            market_price=market_price,
            margin_percent=margin_after_percent,
        )

        if risk_level == "LOW":
            safe_items += 1
        else:
            risky_items += 1

        if risk_level == "HIGH":
            high_risk_items += 1

        total_current_profit += current_profit
        total_projected_profit += projected_profit

        result_rows.append(
            BulkRepricingSimulationRow(
                item_id=str(row["item_id"]),
                title=row.get("title"),
                status=str(row.get("status") or ""),
                current_price=_to_money_str(current_price),
                test_price=_to_money_str(test_price),
                current_profit=_to_money_str(current_profit),
                projected_profit=_to_money_str(projected_profit),
                profit_change=_to_money_str(profit_change),
                min_price=_to_optional_money_str(min_price),
                market_price=_to_optional_money_str(market_price),
                min_price_guard_triggered=min_price_guard_triggered,
                market_price_guard_triggered=market_price_guard_triggered,
                risk_level=risk_level,
                recommendation_reason=recommendation_reason,
            )
        )

    total_profit_change = total_projected_profit - total_current_profit

    return BulkRepricingSimulationResponse(
        business_id=business_id,
        price_drop_percent=_to_money_str(drop_percent),
        limit=limit_i,
        offset=offset_i,
        items_processed=len(result_rows),
        safe_items=safe_items,
        risky_items=risky_items,
        high_risk_items=high_risk_items,
        total_current_profit=_to_money_str(total_current_profit),
        total_projected_profit=_to_money_str(total_projected_profit),
        total_profit_change=_to_money_str(total_profit_change),
        rows=result_rows,
    )

def simulate_repricing_strategy(
    db: Session,
    *,
    business_id: str,
    drop_30_days: Decimal,
    drop_60_days: Decimal,
    drop_90_days: Decimal,
    limit: int,
    offset: int,
) -> RepricingStrategyResponse:

    rows_db = fetch_items_for_repricing_strategy(
        db,
        business_id=business_id,
        limit=limit,
        offset=offset,
    )

    safe_items = 0
    risky_items = 0
    high_risk_items = 0

    total_current_profit = Decimal("0")
    total_projected_profit = Decimal("0")

    result_rows: List[RepricingStrategyRow] = []

    for r in rows_db:

        age_days = int(r["age_days"])

        if age_days >= 90:
            drop_percent = drop_90_days
        elif age_days >= 60:
            drop_percent = drop_60_days
        elif age_days >= 30:
            drop_percent = drop_30_days
        else:
            drop_percent = Decimal("0")

        current_price = Decimal(str(r["suggested_price"]))
        drop_multiplier = Decimal("1") - (drop_percent / Decimal("100"))
        test_price = (current_price * drop_multiplier).quantize(Decimal("0.01"))

        buy_cost = _safe_decimal(r.get("buy_cost"))
        shipping_cost = _safe_decimal(r.get("shipping_cost"))
        packaging_cost = _safe_decimal(r.get("packaging_cost"))
        platform_fee_percent = _safe_decimal(r.get("platform_fee_percent"))
        promo_fee_percent = _safe_decimal(r.get("promo_fee_percent"))

        current_profit = _calculate_projected_profit(
            sale_price=current_price,
            buy_cost=buy_cost,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
            platform_fee_percent=platform_fee_percent,
            promo_fee_percent=promo_fee_percent,
        )

        projected_profit = _calculate_projected_profit(
            sale_price=test_price,
            buy_cost=buy_cost,
            shipping_cost=shipping_cost,
            packaging_cost=packaging_cost,
            platform_fee_percent=platform_fee_percent,
            promo_fee_percent=promo_fee_percent,
        )

        profit_change = projected_profit - current_profit

        margin_percent = Decimal("0")
        if test_price > 0:
            margin_percent = (projected_profit / test_price) * Decimal("100")

        min_price = Decimal(str(r["min_price"])) if r.get("min_price") else None
        market_price = Decimal(str(r["market_price"])) if r.get("market_price") else None

        risk_level = _determine_risk_level(
            test_price=test_price,
            min_price=min_price,
            market_price=market_price,
            margin_percent=margin_percent,
        )

        reason = _determine_reason(
            test_price=test_price,
            min_price=min_price,
            market_price=market_price,
            margin_percent=margin_percent,
        )

        if risk_level == "LOW":
            safe_items += 1
        elif risk_level == "MEDIUM":
            risky_items += 1
        else:
            high_risk_items += 1

        total_current_profit += current_profit
        total_projected_profit += projected_profit

        result_rows.append(
            RepricingStrategyRow(
                item_id=str(r["item_id"]),
                title=r.get("title"),
                status=r.get("status"),
                age_days=age_days,
                current_price=str(current_price),
                test_price=str(test_price),
                current_profit=str(current_profit),
                projected_profit=str(projected_profit),
                profit_change=str(profit_change),
                risk_level=risk_level,
                recommendation_reason=reason,
            )
        )

    total_profit_change = total_projected_profit - total_current_profit

    return RepricingStrategyResponse(
        business_id=business_id,
        items_processed=len(result_rows),
        safe_items=safe_items,
        risky_items=risky_items,
        high_risk_items=high_risk_items,
        total_current_profit=str(total_current_profit),
        total_projected_profit=str(total_projected_profit),
        total_profit_change=str(total_profit_change),
        rows=result_rows,
    )

def analyze_relist_opportunities(
    db: Session,
    *,
    business_id: str,
    limit: int = 200,
) -> RelistOpportunitiesResponse:

    rows_db = fetch_items_for_relist_analysis(
        db,
        business_id=business_id,
        limit=limit,
    )

    relist_now = 0
    relist_with_price_drop = 0
    monitor = 0

    result_rows: List[RelistOpportunityRow] = []

    for r in rows_db:

        age_days = int(r["age_days"])

        suggested_price = r.get("suggested_price")
        market_price = r.get("market_price")

        price_ratio = None
        if suggested_price and market_price:
            try:
                price_ratio = Decimal(suggested_price) / Decimal(market_price)
            except Exception:
                price_ratio = None

        if age_days >= 90:
            bucket = "dead_stock"
        elif age_days >= 60:
            bucket = "slow_mover"
        elif age_days >= 30:
            bucket = "aging"
        else:
            bucket = "fresh"

        if age_days >= 60 and price_ratio and price_ratio >= Decimal("1.10"):
            action = "relist_with_price_drop"
            reason = "slow_mover_overpriced"
            confidence = Decimal("0.85")
            relist_with_price_drop += 1

        elif age_days >= 60:
            action = "relist_now"
            reason = "slow_mover_visibility_drop"
            confidence = Decimal("0.75")
            relist_now += 1

        else:
            action = "monitor"
            reason = "listing_performing_normally"
            confidence = Decimal("0.40")
            monitor += 1

        result_rows.append(
            RelistOpportunityRow(
                item_id=str(r["item_id"]),
                title=r.get("title"),
                status=r.get("status"),
                age_days=age_days,
                suggested_price=suggested_price,
                market_price=market_price,
                inventory_bucket=bucket,
                recommended_action=action,
                confidence_score=confidence,
                reason=reason,
            )
        )

    return RelistOpportunitiesResponse(
        business_id=business_id,
        items_analyzed=len(result_rows),
        relist_now=relist_now,
        relist_with_price_drop=relist_with_price_drop,
        monitor=monitor,
        rows=result_rows,
    )