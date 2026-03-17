# backend/app/business/repo.py

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import BusinessSettings, BusinessUser


DEFAULT_SETTINGS = {
    # Must match DB constraint: only 'ET' or 'EOOD'
    "business_type": "ET",
    "vat_registered": False,
    "vat_percent": Decimal("0"),
    "income_tax_percent": Decimal("0"),
    "currency": "EUR",
    "platform_fee_percent": Decimal("14.0"),
    "promo_fee_percent": Decimal("2.0"),
    "default_shipping_cost": Decimal("6.00"),
    "default_packaging_cost": Decimal("0.50"),
    "target_profit": 5.0,  # column is double precision
    "rounding_mode": "END_99",
    "demand_low_multiplier": 2.0,
    "demand_medium_multiplier": 3.0,
    "demand_high_multiplier": 4.0,
    "main_marketplace": "eBay.de",
    "country_from": "BG",
}


def get_user_role_in_business(db: Session, business_id: UUID, user_id: UUID) -> str | None:
    row = (
        db.query(BusinessUser)
        .filter(
            BusinessUser.business_id == business_id,
            BusinessUser.user_id == user_id,
        )
        .first()
    )
    return row.role if row else None


def get_business_settings(db: Session, business_id: UUID) -> BusinessSettings | None:
    return (
        db.query(BusinessSettings)
        .filter(BusinessSettings.business_id == business_id)
        .first()
    )


def ensure_business_settings(db: Session, business_id: UUID) -> BusinessSettings:
    """
    Option A:
    If a business has no settings row yet, create it with safe defaults.
    This is idempotent.
    """
    existing = get_business_settings(db, business_id)
    if existing:
        return existing

    settings = BusinessSettings(business_id=business_id, **DEFAULT_SETTINGS)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def update_business_settings(db: Session, business_id: UUID, updates: dict) -> BusinessSettings:
    """
    Updates existing settings. If missing, creates first (Option A).
    """
    settings = ensure_business_settings(db, business_id)

    for k, v in updates.items():
        if hasattr(settings, k):
            setattr(settings, k, v)

    db.commit()
    db.refresh(settings)
    return settings