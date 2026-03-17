# backend/app/business/schemas.py

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, UUID4


class BusinessType(str, Enum):
    ET = "ET"
    EOOD = "EOOD"


class RoundingMode(str, Enum):
    NONE = "NONE"
    END_99 = "END_99"


class BusinessSettingsOut(BaseModel):
    business_id: UUID4

    business_type: Optional[BusinessType] = None
    vat_registered: Optional[bool] = None
    vat_percent: Optional[Decimal] = None
    income_tax_percent: Optional[Decimal] = None
    currency: Optional[str] = None

    platform_fee_percent: Optional[Decimal] = None
    promo_fee_percent: Optional[Decimal] = None
    default_shipping_cost: Optional[Decimal] = None
    default_packaging_cost: Optional[Decimal] = None

    target_profit: Optional[float] = None
    rounding_mode: Optional[str] = None

    demand_low_multiplier: Optional[float] = None
    demand_medium_multiplier: Optional[float] = None
    demand_high_multiplier: Optional[float] = None

    main_marketplace: Optional[str] = None
    country_from: Optional[str] = None

    class Config:
        from_attributes = True


class BusinessSettingsUpdate(BaseModel):
    business_type: Optional[BusinessType] = None
    vat_registered: Optional[bool] = None
    vat_percent: Optional[str] = None
    income_tax_percent: Optional[str] = None
    currency: Optional[str] = None

    platform_fee_percent: Optional[str] = None
    promo_fee_percent: Optional[str] = None
    default_shipping_cost: Optional[str] = None
    default_packaging_cost: Optional[str] = None

    target_profit: Optional[float] = Field(default=None, ge=0)
    rounding_mode: Optional[RoundingMode] = None

    demand_low_multiplier: Optional[float] = Field(default=None, ge=0)
    demand_medium_multiplier: Optional[float] = Field(default=None, ge=0)
    demand_high_multiplier: Optional[float] = Field(default=None, ge=0)

    main_marketplace: Optional[str] = None
    country_from: Optional[str] = None