from __future__ import annotations

from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared item profit row (string amounts - handy for simple widgets)
# ---------------------------------------------------------------------------

class FinanceItemProfitRow(BaseModel):
    item_id: str
    sold_at: Optional[str] = None

    title: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    status: Optional[str] = None

    gross_sales: str
    fees: str
    shipping_costs: str
    buy_cost_total: str
    net_profit: str


class TopItemsResponse(BaseModel):
    top_profit_items: List[FinanceItemProfitRow] = Field(default_factory=list)
    top_loss_items: List[FinanceItemProfitRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Ranking / margin analytics
# ---------------------------------------------------------------------------

class MarginItemRow(BaseModel):
    item_id: str
    sold_at: Optional[str] = None

    title: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    status: Optional[str] = None

    gross_sales: Decimal = Field(Decimal("0.00"))
    fees: Decimal = Field(Decimal("0.00"))
    shipping_costs: Decimal = Field(Decimal("0.00"))
    buy_cost_total: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))
    profit_margin_percent: Optional[Decimal] = None


class WorstItemsResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None
    limit: int
    rows: List[MarginItemRow] = Field(default_factory=list)


class LossItemsResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None
    limit: int
    rows: List[MarginItemRow] = Field(default_factory=list)


class LowMarginItemsResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None
    limit: int
    threshold_percent: Decimal = Field(Decimal("15.00"))
    rows: List[MarginItemRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Anomaly analytics
# ---------------------------------------------------------------------------

class FinanceAnomalyItemRow(BaseModel):
    item_id: str
    sold_at: Optional[str] = None

    title: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    status: Optional[str] = None

    gross_sales: Decimal = Field(Decimal("0.00"))
    fees: Decimal = Field(Decimal("0.00"))
    shipping_costs: Decimal = Field(Decimal("0.00"))
    buy_cost_total: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))

    anomaly_type: Literal["high_fee", "high_shipping", "high_buy_cost", "weak_profit"]
    metric_percent: Decimal = Field(Decimal("0.00"))


class FinanceAnomalyResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None
    limit: int
    threshold_percent: Decimal
    rows: List[FinanceAnomalyItemRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Profit summary / timeseries / dashboard
# ---------------------------------------------------------------------------

class ProfitSummaryResponse(BaseModel):
    """
    Ledger-based profit summary.

    Notes:
    - Ledger amounts are signed in DB (SALE positive, costs negative).
    - For API display, cost components are returned as POSITIVE numbers.
    """

    business_id: str = Field(..., description="Business scope")

    gross_sales: Decimal = Field(Decimal("0.00"))
    fees: Decimal = Field(Decimal("0.00"))
    shipping_costs: Decimal = Field(Decimal("0.00"))
    buy_cost_total: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))

    sold_count: int = Field(0, ge=0)
    avg_profit_per_sale: Decimal = Field(Decimal("0.00"))
    profit_margin_percent: Optional[Decimal] = Field(
        None, description="(net_profit / gross_sales) * 100, null when gross_sales = 0"
    )


class ProfitTimeseriesPoint(BaseModel):
    bucket_start: str = Field(..., description="ISO datetime (UTC) marking start of bucket")
    gross_sales: Decimal = Field(Decimal("0.00"))
    fees: Decimal = Field(Decimal("0.00"))
    shipping_costs: Decimal = Field(Decimal("0.00"))
    buy_cost_total: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))
    sold_count: int = Field(0, ge=0)


class ProfitTimeseriesResponse(BaseModel):
    business_id: str
    bucket: Literal["day", "week", "month"]
    start: Optional[str] = None
    end: Optional[str] = None
    points: List[ProfitTimeseriesPoint]


class FinanceDashboardResponse(BaseModel):
    """
    One-call response for the financial dashboard screen.
    """

    business_id: str
    range: Literal["7d", "30d", "90d", "mtd", "ytd", "custom"]

    gross_sales: Decimal = Field(Decimal("0.00"))
    total_costs: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))
    sold_count: int = Field(0, ge=0)
    avg_profit_per_sale: Decimal = Field(Decimal("0.00"))
    profit_margin_percent: Optional[Decimal] = None

    fees: Decimal = Field(Decimal("0.00"))
    shipping_costs: Decimal = Field(Decimal("0.00"))
    buy_cost_total: Decimal = Field(Decimal("0.00"))

    profit_timeseries: ProfitTimeseriesResponse


# ---------------------------------------------------------------------------
# Profit by platform
# ---------------------------------------------------------------------------

class ProfitByPlatformRow(BaseModel):
    platform: str = Field(..., description="Marketplace/platform name (e.g. eBay, Vinted).")

    gross_sales: Decimal = Field(Decimal("0.00"))
    fees: Decimal = Field(Decimal("0.00"))
    shipping_costs: Decimal = Field(Decimal("0.00"))
    buy_cost_total: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))

    sold_count: int = Field(0, ge=0)
    avg_profit_per_sale: Decimal = Field(Decimal("0.00"))
    profit_margin_percent: Optional[Decimal] = None


class ProfitByPlatformResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None
    rows: List[ProfitByPlatformRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-item profit report (A) + item metadata join
# ---------------------------------------------------------------------------

class ItemProfitRow(BaseModel):
    item_id: str
    sold_at: Optional[str] = Field(None, description="ISO datetime (UTC) of SALE entry")

    title: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    status: Optional[str] = None

    gross_sales: Decimal = Field(Decimal("0.00"))
    fees: Decimal = Field(Decimal("0.00"))
    shipping_costs: Decimal = Field(Decimal("0.00"))
    buy_cost_total: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))


class ItemProfitReportResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None

    limit: int
    offset: int
    order: Literal["profit_desc", "profit_asc", "sold_desc", "sold_asc"]

    rows: List[ItemProfitRow]


# ---------------------------------------------------------------------------
# Single item profit details
# ---------------------------------------------------------------------------

class LedgerLine(BaseModel):
    entry_type: str
    amount: Decimal

    kind: Literal["income", "cost"]
    display_amount: Decimal = Field(..., description="Positive for costs, same as amount for income")

    created_at: str = Field(..., description="ISO datetime (UTC)")


class ItemProfitDetailResponse(BaseModel):
    business_id: str
    item_id: str
    start: Optional[str] = None
    end: Optional[str] = None

    title: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    status: Optional[str] = None

    gross_sales: Decimal = Field(Decimal("0.00"))
    fees: Decimal = Field(Decimal("0.00"))
    shipping_costs: Decimal = Field(Decimal("0.00"))
    buy_cost_total: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))

    sold_at: Optional[str] = None
    lines: List[LedgerLine] = Field(default_factory=list)