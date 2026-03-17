from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.finance.schemas import (
    FinanceAnomalyResponse,
    FinanceDashboardResponse,
    ItemProfitDetailResponse,
    ItemProfitReportResponse,
    LossItemsResponse,
    LowMarginItemsResponse,
    ProfitByPlatformResponse,
    ProfitSummaryResponse,
    ProfitTimeseriesResponse,
    TopItemsResponse,
    WorstItemsResponse,
)
from app.finance.service import (
    get_finance_dashboard,
    get_high_buy_cost_items,
    get_high_fee_items,
    get_high_shipping_items,
    get_item_profit_detail,
    get_item_profit_report,
    get_loss_items,
    get_low_margin_items,
    get_profit_by_platform,
    get_profit_summary,
    get_profit_timeseries,
    get_top_items,
    get_weak_profit_items,
    get_worst_items,
)

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/profit-summary", response_model=ProfitSummaryResponse)
def profit_summary(
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_profit_summary(db, business_id=business_id, start=start, end=end)


@router.get("/profit-timeseries", response_model=ProfitTimeseriesResponse)
def profit_timeseries(
    business_id: str,
    bucket: Literal["day", "week", "month"] = "day",
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_profit_timeseries(db, business_id=business_id, bucket=bucket, start=start, end=end)


@router.get("/dashboard", response_model=FinanceDashboardResponse)
def finance_dashboard(
    business_id: str,
    range: Literal["7d", "30d", "90d", "mtd", "ytd", "custom"] = "30d",
    bucket: Literal["day", "week", "month"] = "day",
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_finance_dashboard(
        db,
        business_id=business_id,
        range=range,
        start=start,
        end=end,
        bucket=bucket,
    )


@router.get("/profit/items", response_model=ItemProfitReportResponse)
def profit_items(
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    order: Literal["profit_desc", "profit_asc", "sold_desc", "sold_asc"] = "profit_desc",
    db: Session = Depends(get_db),
):
    return get_item_profit_report(
        db,
        business_id=business_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
        order=order,
    )


@router.get("/profit/items/{item_id}", response_model=ItemProfitDetailResponse)
def profit_item_detail(
    item_id: str,
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_item_profit_detail(
        db,
        business_id=business_id,
        item_id=item_id,
        start=start,
        end=end,
    )


@router.get("/top-items", response_model=TopItemsResponse)
def top_items(
    business_id: str,
    limit: int = 5,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_top_items(db, business_id=business_id, limit=limit, start=start, end=end)


@router.get("/worst-items", response_model=WorstItemsResponse)
def worst_items(
    business_id: str,
    limit: int = 10,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_worst_items(db, business_id=business_id, limit=limit, start=start, end=end)


@router.get("/loss-items", response_model=LossItemsResponse)
def loss_items(
    business_id: str,
    limit: int = 10,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_loss_items(
        db,
        business_id=business_id,
        limit=limit,
        start=start,
        end=end,
    )


@router.get("/low-margin-items", response_model=LowMarginItemsResponse)
def low_margin_items(
    business_id: str,
    threshold_percent: Decimal = Decimal("15.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_low_margin_items(
        db,
        business_id=business_id,
        threshold_percent=threshold_percent,
        limit=limit,
        start=start,
        end=end,
    )


@router.get("/anomalies/high-fee-items", response_model=FinanceAnomalyResponse)
def anomalies_high_fee_items(
    business_id: str,
    threshold_percent: Decimal = Decimal("20.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_high_fee_items(
        db,
        business_id=business_id,
        threshold_percent=threshold_percent,
        limit=limit,
        start=start,
        end=end,
    )


@router.get("/anomalies/high-shipping-items", response_model=FinanceAnomalyResponse)
def anomalies_high_shipping_items(
    business_id: str,
    threshold_percent: Decimal = Decimal("15.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_high_shipping_items(
        db,
        business_id=business_id,
        threshold_percent=threshold_percent,
        limit=limit,
        start=start,
        end=end,
    )


@router.get("/anomalies/high-buy-cost-items", response_model=FinanceAnomalyResponse)
def anomalies_high_buy_cost_items(
    business_id: str,
    threshold_percent: Decimal = Decimal("60.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_high_buy_cost_items(
        db,
        business_id=business_id,
        threshold_percent=threshold_percent,
        limit=limit,
        start=start,
        end=end,
    )


@router.get("/anomalies/weak-profit-items", response_model=FinanceAnomalyResponse)
def anomalies_weak_profit_items(
    business_id: str,
    threshold_percent: Decimal = Decimal("10.00"),
    limit: int = 20,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_weak_profit_items(
        db,
        business_id=business_id,
        threshold_percent=threshold_percent,
        limit=limit,
        start=start,
        end=end,
    )


@router.get("/profit/by-platform", response_model=ProfitByPlatformResponse)
def profit_by_platform(
    business_id: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_profit_by_platform(db, business_id=business_id, start=start, end=end)