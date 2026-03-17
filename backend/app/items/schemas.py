from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Shared numeric parsing (comma/dot safe)
# ---------------------------------------------------------------------------

def _parse_float(v: Any) -> Any:
    """
    Accepts:
      - 5, "5", "5.00", "5,00"
    Returns:
      - float or None
    Leaves:
      - non-numeric as-is (pydantic will raise)
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return None
        s = s.replace(",", ".")
        return float(s)
    return v


# ---------------------------------------------------------------------------
# Item schemas
# ---------------------------------------------------------------------------

class ItemBase(BaseModel):
    title: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    condition: Optional[str] = None
    notes: Optional[str] = None

    buy_cost: Optional[float] = None
    shipping_cost: Optional[float] = None
    packaging_cost: Optional[float] = None

    platform_fee_percent: Optional[float] = None
    promo_fee_percent: Optional[float] = None
    multiplier: Optional[float] = None

    target_profit: Optional[float] = None
    market_price: Optional[float] = None

    shipping_included: Optional[bool] = None

    status: Optional[str] = None

    sale_price: Optional[float] = None
    sold_at: Optional[datetime] = None
    marketplace: Optional[str] = Field(
        default=None,
        description="Optional marketplace for the sale (e.g. EBAY, VINTED). Used when recording Sold ledger entries.",
    )

    _coerce_buy_cost = validator("buy_cost", pre=True, allow_reuse=True)(_parse_float)
    _coerce_shipping_cost = validator("shipping_cost", pre=True, allow_reuse=True)(_parse_float)
    _coerce_packaging_cost = validator("packaging_cost", pre=True, allow_reuse=True)(_parse_float)

    _coerce_platform_fee_percent = validator("platform_fee_percent", pre=True, allow_reuse=True)(_parse_float)
    _coerce_promo_fee_percent = validator("promo_fee_percent", pre=True, allow_reuse=True)(_parse_float)
    _coerce_multiplier = validator("multiplier", pre=True, allow_reuse=True)(_parse_float)

    _coerce_target_profit = validator("target_profit", pre=True, allow_reuse=True)(_parse_float)
    _coerce_market_price = validator("market_price", pre=True, allow_reuse=True)(_parse_float)

    _coerce_sale_price = validator("sale_price", pre=True, allow_reuse=True)(_parse_float)


class ItemCreate(ItemBase):
    title: str = Field(..., description="Human-friendly item title")
    status: Optional[str] = Field(default="Draft")


class ItemUpdate(ItemBase):
    marketplace: Optional[str] = Field(
        default=None,
        description="Optional marketplace for the sale (e.g. EBAY, VINTED).",
    )


class ItemOut(BaseModel):
    item_id: str
    business_id: str

    title: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    condition: Optional[str] = None
    notes: Optional[str] = None

    buy_cost: Optional[float] = None
    shipping_cost: Optional[float] = None
    packaging_cost: Optional[float] = None

    platform_fee_percent: Optional[float] = None
    promo_fee_percent: Optional[float] = None
    multiplier: Optional[float] = None
    target_profit: Optional[float] = None
    shipping_included: Optional[bool] = None

    status: Optional[str] = None
    sale_price: Optional[float] = None
    sold_at: Optional[datetime] = None

    suggested_price: Optional[float] = None
    min_price: Optional[float] = None
    market_price: Optional[float] = None
    estimated_profit: Optional[float] = None
    total_fee_percent: Optional[float] = None

    safe_to_sell: Optional[bool] = None
    safe_to_sell_reasons: Optional[Union[List[Any], Dict[str, Any]]] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status_updated_at: Optional[datetime] = None
    active_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Item events
# ---------------------------------------------------------------------------

class ItemEventOut(BaseModel):
    event_id: str
    item_id: str
    business_id: str
    event_type: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime


class ItemEventsPage(BaseModel):
    item_id: str
    events: List[ItemEventOut]
    limit: int = Field(..., ge=1, le=200)
    next_cursor: Optional[str] = None


# ---------------------------------------------------------------------------
# Items Stats
# ---------------------------------------------------------------------------

class ItemsStatsProfit(BaseModel):
    sum_estimated_profit: float = 0.0
    avg_estimated_profit: float = 0.0


class ItemsStatsPricing(BaseModel):
    avg_total_fee_percent: float = 0.0
    avg_multiplier: float = 0.0
    avg_suggested_price: float = 0.0
    avg_min_price: float = 0.0


class ItemsStatsResponse(BaseModel):
    total_items: int = 0
    by_status: Dict[str, int] = Field(default_factory=dict)
    safe_to_sell: Dict[str, int] = Field(default_factory=dict)
    profit: ItemsStatsProfit = Field(default_factory=ItemsStatsProfit)
    pricing: ItemsStatsPricing = Field(default_factory=ItemsStatsPricing)
    reasons: Dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Inventory intelligence
# ---------------------------------------------------------------------------

class InventoryStatusSummaryRow(BaseModel):
    status: str
    count: int = Field(..., ge=0)


class InventoryStatusSummaryResponse(BaseModel):
    business_id: str
    include_deleted: bool = False
    total_items: int = 0
    rows: List[InventoryStatusSummaryRow] = Field(default_factory=list)


class ItemAgingRow(BaseModel):
    item_id: str
    business_id: str

    title: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    status: Optional[str] = None

    created_at: Optional[str] = None
    active_at: Optional[str] = None
    sold_at: Optional[str] = None
    archived_at: Optional[str] = None
    status_updated_at: Optional[str] = None

    age_days: int = Field(0, ge=0)


class InventoryAgingResponse(BaseModel):
    business_id: str
    include_deleted: bool = False
    only_active: bool = False
    min_age_days: Optional[int] = None
    limit: int
    offset: int
    rows: List[ItemAgingRow] = Field(default_factory=list)