from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

DemandTier = Literal["LOW", "MEDIUM", "HIGH"]
RoundingMode = Literal["NONE", "END_99"]

class ItemBase(BaseModel):
    title: str
    category: Optional[str] = None
    buyCost: float
    demandTier: DemandTier
    multiplier: float
    status: str = "DRAFT"

    shippingCostOverride: Optional[float] = None
    packagingCostOverride: Optional[float] = None

class ItemCreate(ItemBase):
    pass

class ItemUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    buyCost: Optional[float] = None
    demandTier: Optional[DemandTier] = None
    multiplier: Optional[float] = None
    status: Optional[str] = None

    shippingCostOverride: Optional[float] = None
    packagingCostOverride: Optional[float] = None

    # SOLD flow
    salePrice: Optional[float] = None
    soldAt: Optional[datetime] = None

class ItemOut(BaseModel):
    itemId: str
    title: str
    category: Optional[str] = None
    buyCost: float
    demandTier: DemandTier
    multiplier: float
    status: str

    shippingCostOverride: Optional[float] = None
    packagingCostOverride: Optional[float] = None

    # Stored pricing snapshot
    suggestedPrice: Optional[float] = None
    minPrice: Optional[float] = None
    marketPrice: Optional[float] = None
    estimatedProfit: Optional[float] = None
    totalFeePercent: Optional[float] = None

    salePrice: Optional[float] = None
    soldAt: Optional[datetime] = None
    createdAt: Optional[datetime] = None