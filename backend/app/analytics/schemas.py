from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Union

from pydantic import BaseModel, Field


# =========================================================
# Repricing Simulator
# =========================================================


class RepricingSimulationRequest(BaseModel):
    """
    Request body for repricing simulator.

    Example:
    {
        "test_prices": ["44.99", "39.99", "34,99"]
    }
    """

    test_prices: List[Union[str, float, int]] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="List of candidate prices to simulate",
    )


class RepricingSimulationScenario(BaseModel):
    test_price: str

    profit_after: str
    margin_after_percent: str

    profit_change: str
    margin_change_percent: str

    min_price_guard_triggered: bool
    market_price_guard_triggered: bool

    risk_level: str
    recommendation_reason: str


class RepricingSimulationResponse(BaseModel):
    item_id: str
    title: Optional[str] = None

    currency: Optional[str] = None
    status: str

    current_price: str
    current_profit: str
    current_margin_percent: str

    min_price: Optional[str] = None
    market_price: Optional[str] = None

    recommended_price: Optional[str] = None
    recommended_strategy: str

    best_profit_price: Optional[str] = None
    lowest_risk_price: Optional[str] = None

    simulations: List[RepricingSimulationScenario] = Field(default_factory=list)



class BulkRepricingSimulationRequest(BaseModel):
    """
    Request body for bulk repricing simulator.

    Example:
    {
        "price_drop_percent": 10,
        "limit": 50,
        "offset": 0
    }
    """

    price_drop_percent: Union[str, float, int, Decimal] = Field(
        ...,
        description="Percent drop to apply to each item's suggested price",
    )

    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Number of items to simulate",
    )

    offset: int = Field(
        default=0,
        ge=0,
        description="Pagination offset",
    )


class BulkRepricingSimulationRow(BaseModel):
    item_id: str
    title: Optional[str] = None
    status: str

    current_price: str
    test_price: str

    current_profit: str
    projected_profit: str
    profit_change: str

    min_price: Optional[str] = None
    market_price: Optional[str] = None

    min_price_guard_triggered: bool
    market_price_guard_triggered: bool

    risk_level: str
    recommendation_reason: str


class BulkRepricingSimulationResponse(BaseModel):
    business_id: str
    price_drop_percent: str
    limit: int
    offset: int

    items_processed: int
    safe_items: int
    risky_items: int
    high_risk_items: int

    total_current_profit: str
    total_projected_profit: str
    total_profit_change: str

    rows: List[BulkRepricingSimulationRow] = Field(default_factory=list)


# =========================================================
# Sell Through
# =========================================================


class SellThroughResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None

    items_sold: int = Field(0, ge=0)
    items_created: int = Field(0, ge=0)
    sell_through_rate: Decimal = Field(Decimal("0.00"))


# =========================================================
# Time To Sell
# =========================================================


class TimeToSellRow(BaseModel):
    item_id: str
    title: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    active_at: Optional[str] = None
    sold_at: Optional[str] = None
    days_to_sell: int = Field(0, ge=0)


class TimeToSellResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None

    items_sold: int = Field(0, ge=0)
    avg_days_to_sell: Decimal = Field(Decimal("0.00"))
    median_days_to_sell: Decimal = Field(Decimal("0.00"))
    fastest_sale_days: Optional[int] = Field(default=None, ge=0)
    slowest_sale_days: Optional[int] = Field(default=None, ge=0)

    rows: List[TimeToSellRow] = Field(default_factory=list)


# =========================================================
# Marketplace Analytics
# =========================================================


class MarketplaceAnalyticsRow(BaseModel):
    marketplace: str

    items_sold: int = Field(0, ge=0)
    gross_sales: Decimal = Field(Decimal("0.00"))
    net_profit: Decimal = Field(Decimal("0.00"))
    avg_profit_per_sale: Decimal = Field(Decimal("0.00"))
    avg_days_to_sell: Decimal = Field(Decimal("0.00"))


class MarketplaceAnalyticsResponse(BaseModel):
    business_id: str
    start: Optional[str] = None
    end: Optional[str] = None
    rows: List[MarketplaceAnalyticsRow] = Field(default_factory=list)


# =========================================================
# Inventory Health
# =========================================================


class InventoryHealthResponse(BaseModel):
    business_id: str
    as_of: str

    total_active_inventory: int = Field(0, ge=0)

    fresh_count: int = Field(0, ge=0)
    aging_count: int = Field(0, ge=0)
    slow_mover_count: int = Field(0, ge=0)
    dead_stock_count: int = Field(0, ge=0)

    dead_stock_ratio: Decimal = Field(Decimal("0.00"))


class InventoryHealthItemRow(BaseModel):
    item_id: str
    title: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    active_at: Optional[str] = None
    age_days: int = Field(0, ge=0)


class InventoryHealthItemsResponse(BaseModel):
    business_id: str
    bucket: str
    limit: int
    offset: int
    rows: List[InventoryHealthItemRow] = Field(default_factory=list)


# =========================================================
# Pricing Opportunities
# =========================================================


class PricingOpportunityRow(BaseModel):
    item_id: str
    title: Optional[str] = None
    status: Optional[str] = None

    market_price: Optional[Decimal] = None
    suggested_price: Optional[Decimal] = None

    age_days: int = Field(0, ge=0)
    pricing_signal: str


class PricingOpportunitiesResponse(BaseModel):
    business_id: str
    signal: str
    limit: int
    offset: int
    rows: List[PricingOpportunityRow] = Field(default_factory=list)


# =========================================================
# Price Drop Recommendations
# =========================================================


class PriceDropRecommendationRow(BaseModel):
    item_id: str
    title: Optional[str] = None
    status: Optional[str] = None

    age_days: int = Field(0, ge=0)

    current_price: Optional[Decimal] = None
    min_price: Optional[Decimal] = None
    market_price: Optional[Decimal] = None

    recommended_price: Decimal = Field(Decimal("0.00"))
    drop_percent: Decimal = Field(Decimal("0.00"))
    reason: str


class PriceDropRecommendationsResponse(BaseModel):
    business_id: str
    limit: int
    offset: int
    rows: List[PriceDropRecommendationRow] = Field(default_factory=list)

    # =========================================================
# Intelligent Repricing Strategy
# =========================================================

class RepricingStrategyRequest(BaseModel):
    """
    Age-based repricing strategy simulation.
    """

    drop_30_days: Decimal = Field(default=Decimal("5"))
    drop_60_days: Decimal = Field(default=Decimal("10"))
    drop_90_days: Decimal = Field(default=Decimal("15"))

    limit: int = Field(default=200, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class RepricingStrategyRow(BaseModel):

    item_id: str
    title: Optional[str] = None
    status: str

    age_days: int

    current_price: str
    test_price: str

    current_profit: str
    projected_profit: str
    profit_change: str

    risk_level: str
    recommendation_reason: str


class RepricingStrategyResponse(BaseModel):

    business_id: str

    items_processed: int
    safe_items: int
    risky_items: int
    high_risk_items: int

    total_current_profit: str
    total_projected_profit: str
    total_profit_change: str

    rows: List[RepricingStrategyRow] = Field(default_factory=list)

    # =========================================================
# Relist Opportunities
# =========================================================

class RelistOpportunityRow(BaseModel):

    item_id: str
    title: Optional[str] = None
    status: str

    age_days: int

    suggested_price: Optional[Decimal] = None
    market_price: Optional[Decimal] = None

    inventory_bucket: Optional[str] = None

    recommended_action: str
    confidence_score: Decimal

    reason: str


class RelistOpportunitiesResponse(BaseModel):

    business_id: str

    items_analyzed: int

    relist_now: int
    relist_with_price_drop: int
    monitor: int

    rows: List[RelistOpportunityRow] = Field(default_factory=list)
    