# backend/app/business/routes.py

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.repo import get_first_business_id
from app.business.repo import ensure_business_settings, update_business_settings
from app.db import get_db
from app.business.schemas import BusinessSettingsOut, BusinessSettingsUpdate

router = APIRouter(prefix="/business", tags=["business"])


def _parse_decimal_str(v: Optional[str]) -> Optional[Decimal]:
    if v is None:
        return None
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=f"Invalid decimal value: {v}")


@router.get("/settings", response_model=BusinessSettingsOut)
def get_settings(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    business_id = get_first_business_id(db, user_id=current_user.id)
    if not business_id:
        raise HTTPException(status_code=400, detail="No business linked to user.")

    settings = ensure_business_settings(db, business_id)
    return settings


@router.put("/settings", response_model=BusinessSettingsOut)
def put_settings(
    payload: BusinessSettingsUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    business_id = get_first_business_id(db, user_id=current_user.id)
    if not business_id:
        raise HTTPException(status_code=400, detail="No business linked to user.")

    data: dict[str, Any] = payload.model_dump(exclude_unset=True)

    # Convert enums to raw DB strings
    if "business_type" in data and hasattr(data["business_type"], "value"):
        data["business_type"] = data["business_type"].value
    if "rounding_mode" in data and hasattr(data["rounding_mode"], "value"):
        data["rounding_mode"] = data["rounding_mode"].value

    # Parse decimals for numeric columns
    for k in (
        "vat_percent",
        "income_tax_percent",
        "platform_fee_percent",
        "promo_fee_percent",
        "default_shipping_cost",
        "default_packaging_cost",
    ):
        if k in data:
            data[k] = _parse_decimal_str(data[k])

    settings = update_business_settings(db, business_id, data)
    return settings