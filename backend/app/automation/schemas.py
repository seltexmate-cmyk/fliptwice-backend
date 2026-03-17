from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class RelistPlanItem(BaseModel):

    item_id: str
    title: Optional[str] = None
    reason: str


class RelistPlanDay(BaseModel):

    day_index: int

    relist_now: List[RelistPlanItem] = Field(default_factory=list)

    relist_with_price_drop: List[RelistPlanItem] = Field(default_factory=list)


class RelistPlanRequest(BaseModel):

    days: int = Field(default=7, ge=1, le=30)

    daily_relist_limit: int = Field(default=10, ge=1, le=50)

    daily_price_drop_limit: int = Field(default=5, ge=1, le=50)


class RelistPlanResponse(BaseModel):

    business_id: str

    days: int

    daily_relist_limit: int
    daily_price_drop_limit: int

    plan: List[RelistPlanDay] = Field(default_factory=list)