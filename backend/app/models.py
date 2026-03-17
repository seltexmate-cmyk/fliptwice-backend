import uuid
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    func,
    Numeric,
    Text,
    Float,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)

    # ✅ matches DB
    password_hash = Column(String(255), nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)

    # ✅ matches DB (no updated_at)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Business(Base):
    __tablename__ = "businesses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False)
    country_code = Column(String(10), nullable=False)
    currency_code = Column(String(10), nullable=False)
    vat_enabled = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BusinessUser(Base):
    __tablename__ = "business_users"

    # ✅ composite PK (no id column)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)

    role = Column(String(50), nullable=False, default="admin")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BusinessSettings(Base):
    __tablename__ = "business_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, unique=True)

    business_type = Column(String(50), nullable=False)
    vat_registered = Column(Boolean, nullable=False, default=False)
    vat_percent = Column(Numeric(10, 2), nullable=False, server_default="0")
    income_tax_percent = Column(Numeric(10, 2), nullable=False, server_default="0")
    currency = Column(String(10), nullable=False, server_default="EUR")

    platform_fee_percent = Column(Numeric(6, 2), nullable=False, server_default="0")
    promo_fee_percent = Column(Numeric(6, 2), nullable=False, server_default="0")
    default_shipping_cost = Column(Numeric(10, 2), nullable=False, server_default="0")
    default_packaging_cost = Column(Numeric(10, 2), nullable=False, server_default="0")

    country_from = Column(String(10), nullable=True)
    main_marketplace = Column(String(50), nullable=True)

    target_profit = Column(Float, nullable=False, server_default="0")
    rounding_mode = Column(String(20), nullable=False, server_default="NONE")

    demand_low_multiplier = Column(Float, nullable=False, server_default="1")
    demand_medium_multiplier = Column(Float, nullable=False, server_default="1")
    demand_high_multiplier = Column(Float, nullable=False, server_default="1")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


# -------------------------------------------------------------------
# NEW: Items + snapshot + safe_to_sell
# -------------------------------------------------------------------

class Item(Base):
    """
    Item stores an immutable pricing snapshot at creation time.
    The snapshot MUST NOT be recomputed automatically when settings change.
    """
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)

    title = Column(String(255), nullable=False)

    # Optional lifecycle/status (keep if your DB has it)
    status = Column(String(20), nullable=False, server_default="ACTIVE")

    # Snapshot fields (immutable)
    demand_tier = Column(String(20), nullable=False)
    multiplier = Column(Float, nullable=False, server_default="1")

    buy_cost = Column(Numeric(10, 2), nullable=False)

    suggested_price = Column(Numeric(10, 2), nullable=False)
    min_price = Column(Numeric(10, 2), nullable=False)
    market_price = Column(Numeric(10, 2), nullable=True)

    total_fee_percent = Column(Numeric(6, 2), nullable=False, server_default="0")
    estimated_profit = Column(Numeric(10, 2), nullable=False, server_default="0")

    # NEW snapshot safety fields
    safe_to_sell = Column(Boolean, nullable=True)
    # store as JSONB so we can evolve structure without migrations
    # example: {"reasons": ["BELOW_TARGET_PROFIT", "BELOW_MIN_PRICE"], "version": 1}
    safe_to_sell_reasons = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    sold_at = Column(DateTime(timezone=True), nullable=True)


class ItemStatusEvent(Base):
    """
    Audit trail for item status transitions.
    """
    __tablename__ = "item_status_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id"), nullable=False, index=True)

    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)

    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())