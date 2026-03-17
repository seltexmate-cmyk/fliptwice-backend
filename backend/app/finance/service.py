from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.finance.repo import (
    fetch_item_ledger_lines,
    fetch_item_profit_report,
    fetch_item_profit_summary,
    fetch_items_profit_aggregate_for_ranking,
    fetch_profit_by_platform,
    fetch_profit_summary,
    fetch_profit_timeseries,
)
from app.finance.schemas import (
    FinanceAnomalyItemRow,
    FinanceAnomalyResponse,
    FinanceDashboardResponse,
    FinanceItemProfitRow,
    ItemProfitDetailResponse,
    ItemProfitReportResponse,
    ItemProfitRow,
    LedgerLine,
    LossItemsResponse,
    LowMarginItemsResponse,
    MarginItemRow,
    ProfitByPlatformResponse,
    ProfitByPlatformRow,
    ProfitSummaryResponse,
    ProfitTimeseriesPoint,
    ProfitTimeseriesResponse,
    TopItemsResponse,
    WorstItemsResponse,
)


def _parse_yyyy_mm_dd(value: str) -> date:
    return date.fromisoformat(value)


def _q2(value: Optional[Decimal]) -> Decimal:
    return (value or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money_str(value: Optional[Decimal]) -> str:
    return str(_q2(value))


def _to_start_end_datetimes(
    start: Optional[str],
    end: Optional[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Convert start/end (YYYY-MM-DD) into [start_dt, end_dt) datetimes in UTC.
    - start_dt inclusive at 00:00:00
    - end_dt exclusive at next day 00:00:00 (if end provided)
    """
    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None

    if start:
        d = _parse_yyyy_mm_dd(start)
        start_dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

    if end:
        d = _parse_yyyy_mm_dd(end)
        end_next = d + timedelta(days=1)
        end_dt = datetime(end_next.year, end_next.month, end_next.day, tzinfo=timezone.utc)

    return start_dt, end_dt


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _line_kind_and_display(entry_type: str, signed_amount: Decimal) -> tuple[str, Decimal]:
    et = (entry_type or "").upper().strip()
    if et == "SALE":
        return "income", signed_amount
    return "cost", abs(signed_amount)


def _margin_percent(gross_sales: Decimal, net_profit: Decimal) -> Optional[Decimal]:
    if gross_sales == 0:
        return None
    return (net_profit / gross_sales) * Decimal("100")


def _component_percent(component_value: Decimal, gross_sales: Decimal) -> Optional[Decimal]:
    if gross_sales == 0:
        return None
    return (component_value / gross_sales) * Decimal("100")


def _normalize_margin_row(r: dict) -> MarginItemRow:
    gross_sales = Decimal(r["gross_sales"])
    fees_signed = Decimal(r["fees"])
    shipping_signed = Decimal(r["shipping_costs"])
    buy_signed = Decimal(r["buy_cost_total"])
    net_profit = Decimal(r["net_profit"])
    margin = _margin_percent(gross_sales, net_profit)

    return MarginItemRow(
        item_id=str(r["item_id"]),
        sold_at=_iso_utc(r.get("sold_at")),
        title=r.get("title"),
        sku=r.get("sku"),
        brand=r.get("brand"),
        size=r.get("size"),
        status=r.get("status"),
        gross_sales=_q2(gross_sales),
        fees=_q2(abs(fees_signed)),
        shipping_costs=_q2(abs(shipping_signed)),
        buy_cost_total=_q2(abs(buy_signed)),
        net_profit=_q2(net_profit),
        profit_margin_percent=_q2(margin) if margin is not None else None,
    )


def _normalize_anomaly_row(
    r: dict,
    *,
    anomaly_type: Literal["high_fee", "high_shipping", "high_buy_cost", "weak_profit"],
    metric_percent: Decimal,
) -> FinanceAnomalyItemRow:
    gross_sales = Decimal(r["gross_sales"])
    fees_signed = Decimal(r["fees"])
    shipping_signed = Decimal(r["shipping_costs"])
    buy_signed = Decimal(r["buy_cost_total"])
    net_profit = Decimal(r["net_profit"])

    return FinanceAnomalyItemRow(
        item_id=str(r["item_id"]),
        sold_at=_iso_utc(r.get("sold_at")),
        title=r.get("title"),
        sku=r.get("sku"),
        brand=r.get("brand"),
        size=r.get("size"),
        status=r.get("status"),
        gross_sales=_q2(gross_sales),
        fees=_q2(abs(fees_signed)),
        shipping_costs=_q2(abs(shipping_signed)),
        buy_cost_total=_q2(abs(buy_signed)),
        net_profit=_q2(net_profit),
        anomaly_type=anomaly_type,
        metric_percent=_q2(metric_percent),
    )


def _get_anomaly_rows(
    db: Session,
    *,
    business_id: str,
    start: Optional[str],
    end: Optional[str],
    limit: int,
    threshold_percent: Decimal,
    anomaly_type: Literal["high_fee", "high_shipping", "high_buy_cost", "weak_profit"],
) -> FinanceAnomalyResponse:
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 20
    limit_i = max(1, min(limit_i, 100))

    threshold = _q2(Decimal(threshold_percent))

    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows = fetch_items_profit_aggregate_for_ranking(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    matches: list[FinanceAnomalyItemRow] = []

    for r in rows:
        gross_sales = Decimal(r["gross_sales"])
        if gross_sales == 0:
            continue

        fees = abs(Decimal(r["fees"]))
        shipping_costs = abs(Decimal(r["shipping_costs"]))
        buy_cost_total = abs(Decimal(r["buy_cost_total"]))
        net_profit = Decimal(r["net_profit"])

        metric_percent: Optional[Decimal] = None
        include = False

        if anomaly_type == "high_fee":
            metric_percent = _component_percent(fees, gross_sales)
            include = metric_percent is not None and metric_percent >= threshold
        elif anomaly_type == "high_shipping":
            metric_percent = _component_percent(shipping_costs, gross_sales)
            include = metric_percent is not None and metric_percent >= threshold
        elif anomaly_type == "high_buy_cost":
            metric_percent = _component_percent(buy_cost_total, gross_sales)
            include = metric_percent is not None and metric_percent >= threshold
        elif anomaly_type == "weak_profit":
            metric_percent = _margin_percent(gross_sales, net_profit)
            include = metric_percent is not None and metric_percent <= threshold
        else:
            raise ValueError("Invalid anomaly_type")

        if include and metric_percent is not None:
            matches.append(
                _normalize_anomaly_row(
                    r,
                    anomaly_type=anomaly_type,
                    metric_percent=metric_percent,
                )
            )

    reverse = anomaly_type != "weak_profit"
    matches = sorted(matches, key=lambda x: x.metric_percent, reverse=reverse)[:limit_i]

    return FinanceAnomalyResponse(
        business_id=business_id,
        start=start,
        end=end,
        limit=limit_i,
        threshold_percent=threshold,
        rows=matches,
    )


# ---------------------------------------------------------------------------
# Summary + Timeseries + Dashboard
# ---------------------------------------------------------------------------

def get_profit_summary(
    db: Session,
    *,
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> ProfitSummaryResponse:
    start_dt, end_dt = _to_start_end_datetimes(start, end)
    row = fetch_profit_summary(db, business_id=business_id, start_dt=start_dt, end_dt=end_dt)

    gross_sales = Decimal(row["gross_sales"])
    fees_signed = Decimal(row["fees"])
    shipping_signed = Decimal(row["shipping_costs"])
    buy_cost_signed = Decimal(row["buy_cost_total"])
    net_profit = Decimal(row["net_profit"])
    sold_count = int(row["sold_count"])

    fees = abs(fees_signed)
    shipping_costs = abs(shipping_signed)
    buy_cost_total = abs(buy_cost_signed)

    avg_profit_per_sale = Decimal("0")
    if sold_count > 0:
        avg_profit_per_sale = net_profit / Decimal(sold_count)

    profit_margin_percent = _margin_percent(gross_sales, net_profit)

    return ProfitSummaryResponse(
        business_id=business_id,
        gross_sales=_q2(gross_sales),
        fees=_q2(fees),
        shipping_costs=_q2(shipping_costs),
        buy_cost_total=_q2(buy_cost_total),
        net_profit=_q2(net_profit),
        sold_count=sold_count,
        avg_profit_per_sale=_q2(avg_profit_per_sale),
        profit_margin_percent=_q2(profit_margin_percent) if profit_margin_percent is not None else None,
    )


def get_profit_timeseries(
    db: Session,
    *,
    business_id: str,
    bucket: Literal["day", "week", "month"] = "day",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> ProfitTimeseriesResponse:
    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows = fetch_profit_timeseries(
        db,
        business_id=business_id,
        bucket=bucket,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    points: list[ProfitTimeseriesPoint] = []
    for r in rows:
        gross_sales = Decimal(r["gross_sales"])
        fees = abs(Decimal(r["fees"]))
        shipping_costs = abs(Decimal(r["shipping_costs"]))
        buy_cost_total = abs(Decimal(r["buy_cost_total"]))
        net_profit = Decimal(r["net_profit"])
        sold_count = int(r["sold_count"])

        points.append(
            ProfitTimeseriesPoint(
                bucket_start=_iso_utc(r["bucket_start"]) or "",
                gross_sales=_q2(gross_sales),
                fees=_q2(fees),
                shipping_costs=_q2(shipping_costs),
                buy_cost_total=_q2(buy_cost_total),
                net_profit=_q2(net_profit),
                sold_count=sold_count,
            )
        )

    return ProfitTimeseriesResponse(
        business_id=business_id,
        bucket=bucket,
        start=start,
        end=end,
        points=points,
    )


def _range_to_start_end(
    range_key: Literal["7d", "30d", "90d", "mtd", "ytd", "custom"],
    start: Optional[str],
    end: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[datetime], Optional[datetime]]:
    if range_key == "custom":
        start_dt, end_dt = _to_start_end_datetimes(start, end)
        return start, end, start_dt, end_dt

    today = datetime.now(timezone.utc).date()

    if range_key == "7d":
        start_date = today - timedelta(days=6)
        end_date = today
    elif range_key == "30d":
        start_date = today - timedelta(days=29)
        end_date = today
    elif range_key == "90d":
        start_date = today - timedelta(days=89)
        end_date = today
    elif range_key == "mtd":
        start_date = date(today.year, today.month, 1)
        end_date = today
    elif range_key == "ytd":
        start_date = date(today.year, 1, 1)
        end_date = today
    else:
        raise ValueError("Invalid range")

    start_str = start_date.isoformat()
    end_str = end_date.isoformat()
    start_dt, end_dt = _to_start_end_datetimes(start_str, end_str)
    return start_str, end_str, start_dt, end_dt


def get_finance_dashboard(
    db: Session,
    *,
    business_id: str,
    range: Literal["7d", "30d", "90d", "mtd", "ytd", "custom"] = "30d",
    start: Optional[str] = None,
    end: Optional[str] = None,
    bucket: Literal["day", "week", "month"] = "day",
) -> FinanceDashboardResponse:
    start_str, end_str, start_dt, end_dt = _range_to_start_end(range, start, end)

    row = fetch_profit_summary(db, business_id=business_id, start_dt=start_dt, end_dt=end_dt)

    gross_sales = Decimal(row["gross_sales"])
    fees = abs(Decimal(row["fees"]))
    shipping_costs = abs(Decimal(row["shipping_costs"]))
    buy_cost_total = abs(Decimal(row["buy_cost_total"]))
    net_profit = Decimal(row["net_profit"])
    sold_count = int(row["sold_count"])

    total_costs = fees + shipping_costs + buy_cost_total

    avg_profit_per_sale = Decimal("0")
    if sold_count > 0:
        avg_profit_per_sale = net_profit / Decimal(sold_count)

    profit_margin_percent = _margin_percent(gross_sales, net_profit)

    series = get_profit_timeseries(
        db,
        business_id=business_id,
        bucket=bucket,
        start=start_str,
        end=end_str,
    )

    return FinanceDashboardResponse(
        business_id=business_id,
        range=range,
        gross_sales=_q2(gross_sales),
        total_costs=_q2(total_costs),
        net_profit=_q2(net_profit),
        sold_count=sold_count,
        avg_profit_per_sale=_q2(avg_profit_per_sale),
        profit_margin_percent=_q2(profit_margin_percent) if profit_margin_percent is not None else None,
        fees=_q2(fees),
        shipping_costs=_q2(shipping_costs),
        buy_cost_total=_q2(buy_cost_total),
        profit_timeseries=series,
    )


# ---------------------------------------------------------------------------
# Per-item report + item detail
# ---------------------------------------------------------------------------

def get_item_profit_report(
    db: Session,
    *,
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    order: Literal["profit_desc", "profit_asc", "sold_desc", "sold_asc"] = "profit_desc",
) -> ItemProfitReportResponse:
    try:
        limit_i = int(limit)
        offset_i = int(offset)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pagination params: {exc}")

    limit_i = max(1, min(limit_i, 200))
    offset_i = max(0, offset_i)

    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows = fetch_item_profit_report(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=limit_i,
        offset=offset_i,
        order=order,
    )

    out_rows: list[ItemProfitRow] = []
    for r in rows:
        gross_sales = Decimal(r["gross_sales"])
        fees = abs(Decimal(r["fees"]))
        shipping_costs = abs(Decimal(r["shipping_costs"]))
        buy_cost_total = abs(Decimal(r["buy_cost_total"]))
        net_profit = Decimal(r["net_profit"])

        out_rows.append(
            ItemProfitRow(
                item_id=str(r["item_id"]),
                sold_at=_iso_utc(r["sold_at"]),
                title=r.get("title"),
                sku=r.get("sku"),
                brand=r.get("brand"),
                size=r.get("size"),
                status=r.get("status"),
                gross_sales=_q2(gross_sales),
                fees=_q2(fees),
                shipping_costs=_q2(shipping_costs),
                buy_cost_total=_q2(buy_cost_total),
                net_profit=_q2(net_profit),
            )
        )

    return ItemProfitReportResponse(
        business_id=business_id,
        start=start,
        end=end,
        limit=limit_i,
        offset=offset_i,
        order=order,
        rows=out_rows,
    )


def get_item_profit_detail(
    db: Session,
    *,
    business_id: str,
    item_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> ItemProfitDetailResponse:
    start_dt, end_dt = _to_start_end_datetimes(start, end)

    summary = fetch_item_profit_summary(
        db,
        business_id=business_id,
        item_id=item_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Item not found in ledger for this business")

    lines_db = fetch_item_ledger_lines(
        db,
        business_id=business_id,
        item_id=item_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    gross_sales = Decimal(summary["gross_sales"])
    fees = abs(Decimal(summary["fees"]))
    shipping_costs = abs(Decimal(summary["shipping_costs"]))
    buy_cost_total = abs(Decimal(summary["buy_cost_total"]))
    net_profit = Decimal(summary["net_profit"])

    lines: list[LedgerLine] = []
    for l in lines_db:
        entry_type = str(l["entry_type"])
        signed_amount = Decimal(l["amount"] or 0)
        kind, display_amount = _line_kind_and_display(entry_type, signed_amount)

        lines.append(
            LedgerLine(
                entry_type=entry_type,
                amount=_q2(signed_amount),
                kind=kind,
                display_amount=_q2(display_amount),
                created_at=_iso_utc(l["created_at"]) or "",
            )
        )

    return ItemProfitDetailResponse(
        business_id=business_id,
        item_id=item_id,
        start=start,
        end=end,
        title=summary.get("title"),
        sku=summary.get("sku"),
        brand=summary.get("brand"),
        size=summary.get("size"),
        status=summary.get("status"),
        gross_sales=_q2(gross_sales),
        fees=_q2(fees),
        shipping_costs=_q2(shipping_costs),
        buy_cost_total=_q2(buy_cost_total),
        net_profit=_q2(net_profit),
        sold_at=_iso_utc(summary.get("sold_at")),
        lines=lines,
    )


# ---------------------------------------------------------------------------
# Top items (profit / loss)
# ---------------------------------------------------------------------------

def get_top_items(
    db: Session,
    *,
    business_id: str,
    limit: int = 5,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> TopItemsResponse:
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 5
    limit_i = max(1, min(limit_i, 50))

    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows = fetch_items_profit_aggregate_for_ranking(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    normalized: list[FinanceItemProfitRow] = []
    for r in rows:
        gross_sales = Decimal(r["gross_sales"])
        fees_signed = Decimal(r["fees"])
        shipping_signed = Decimal(r["shipping_costs"])
        buy_signed = Decimal(r["buy_cost_total"])
        net_profit = Decimal(r["net_profit"])

        normalized.append(
            FinanceItemProfitRow(
                item_id=str(r["item_id"]),
                sold_at=_iso_utc(r.get("sold_at")),
                title=r.get("title"),
                sku=r.get("sku"),
                brand=r.get("brand"),
                size=r.get("size"),
                status=r.get("status"),
                gross_sales=_money_str(gross_sales),
                fees=_money_str(abs(fees_signed)),
                shipping_costs=_money_str(abs(shipping_signed)),
                buy_cost_total=_money_str(abs(buy_signed)),
                net_profit=_money_str(net_profit),
            )
        )

    def _dp(v: FinanceItemProfitRow) -> Decimal:
        try:
            return Decimal(v.net_profit)
        except Exception:
            return Decimal("0")

    profit_only = [x for x in normalized if _dp(x) > 0]
    loss_only = [x for x in normalized if _dp(x) < 0]

    top_profit = sorted(profit_only, key=_dp, reverse=True)[:limit_i]
    top_loss = sorted(loss_only, key=_dp)[:limit_i]

    return TopItemsResponse(top_profit_items=top_profit, top_loss_items=top_loss)


def get_worst_items(
    db: Session,
    *,
    business_id: str,
    limit: int = 10,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> WorstItemsResponse:
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 10

    limit_i = max(1, min(limit_i, 100))

    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows = fetch_items_profit_aggregate_for_ranking(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    normalized = [_normalize_margin_row(r) for r in rows]
    worst_rows = sorted(normalized, key=lambda x: x.net_profit)[:limit_i]

    return WorstItemsResponse(
        business_id=business_id,
        start=start,
        end=end,
        limit=limit_i,
        rows=worst_rows,
    )


def get_loss_items(
    db: Session,
    *,
    business_id: str,
    limit: int = 10,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> LossItemsResponse:
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 10

    limit_i = max(1, min(limit_i, 100))

    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows = fetch_items_profit_aggregate_for_ranking(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    normalized = [_normalize_margin_row(r) for r in rows]
    loss_rows = [x for x in normalized if x.net_profit < 0]
    loss_rows = sorted(loss_rows, key=lambda x: x.net_profit)[:limit_i]

    return LossItemsResponse(
        business_id=business_id,
        start=start,
        end=end,
        limit=limit_i,
        rows=loss_rows,
    )


def get_low_margin_items(
    db: Session,
    *,
    business_id: str,
    threshold_percent: Decimal = Decimal("15.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> LowMarginItemsResponse:
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 20
    limit_i = max(1, min(limit_i, 100))

    threshold = _q2(Decimal(threshold_percent))

    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows = fetch_items_profit_aggregate_for_ranking(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    normalized = [_normalize_margin_row(r) for r in rows]

    low_margin_rows = [
        x
        for x in normalized
        if x.profit_margin_percent is not None and x.profit_margin_percent <= threshold
    ]
    low_margin_rows = sorted(
        low_margin_rows,
        key=lambda x: (x.profit_margin_percent if x.profit_margin_percent is not None else Decimal("999999"))
    )[:limit_i]

    return LowMarginItemsResponse(
        business_id=business_id,
        start=start,
        end=end,
        limit=limit_i,
        threshold_percent=threshold,
        rows=low_margin_rows,
    )


# ---------------------------------------------------------------------------
# Anomaly analytics
# ---------------------------------------------------------------------------

def get_high_fee_items(
    db: Session,
    *,
    business_id: str,
    threshold_percent: Decimal = Decimal("20.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> FinanceAnomalyResponse:
    return _get_anomaly_rows(
        db,
        business_id=business_id,
        start=start,
        end=end,
        limit=limit,
        threshold_percent=threshold_percent,
        anomaly_type="high_fee",
    )


def get_high_shipping_items(
    db: Session,
    *,
    business_id: str,
    threshold_percent: Decimal = Decimal("15.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> FinanceAnomalyResponse:
    return _get_anomaly_rows(
        db,
        business_id=business_id,
        start=start,
        end=end,
        limit=limit,
        threshold_percent=threshold_percent,
        anomaly_type="high_shipping",
    )


def get_high_buy_cost_items(
    db: Session,
    *,
    business_id: str,
    threshold_percent: Decimal = Decimal("60.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> FinanceAnomalyResponse:
    return _get_anomaly_rows(
        db,
        business_id=business_id,
        start=start,
        end=end,
        limit=limit,
        threshold_percent=threshold_percent,
        anomaly_type="high_buy_cost",
    )


def get_weak_profit_items(
    db: Session,
    *,
    business_id: str,
    threshold_percent: Decimal = Decimal("10.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> FinanceAnomalyResponse:
    return _get_anomaly_rows(
        db,
        business_id=business_id,
        start=start,
        end=end,
        limit=limit,
        threshold_percent=threshold_percent,
        anomaly_type="weak_profit",
    )


# ---------------------------------------------------------------------------
# Profit by platform
# ---------------------------------------------------------------------------

def get_profit_by_platform(
    db: Session,
    *,
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> ProfitByPlatformResponse:
    start_dt, end_dt = _to_start_end_datetimes(start, end)

    rows = fetch_profit_by_platform(
        db,
        business_id=business_id,
        start_dt=start_dt,
        end_dt=end_dt,
    )

    out: list[ProfitByPlatformRow] = []
    for r in rows:
        gross_sales = Decimal(r["gross_sales"])
        fees = abs(Decimal(r["fees"]))
        shipping_costs = abs(Decimal(r["shipping_costs"]))
        buy_cost_total = abs(Decimal(r["buy_cost_total"]))
        net_profit = Decimal(r["net_profit"])
        sold_count = int(r["sold_count"])

        avg_profit_per_sale = Decimal("0")
        if sold_count > 0:
            avg_profit_per_sale = net_profit / Decimal(sold_count)

        profit_margin_percent = _margin_percent(gross_sales, net_profit)

        out.append(
            ProfitByPlatformRow(
                platform=str(r["platform"] or "Unknown"),
                gross_sales=_q2(gross_sales),
                fees=_q2(fees),
                shipping_costs=_q2(shipping_costs),
                buy_cost_total=_q2(buy_cost_total),
                net_profit=_q2(net_profit),
                sold_count=sold_count,
                avg_profit_per_sale=_q2(avg_profit_per_sale),
                profit_margin_percent=_q2(profit_margin_percent) if profit_margin_percent is not None else None,
            )
        )

    return ProfitByPlatformResponse(
        business_id=business_id,
        start=start,
        end=end,
        rows=out,
    )