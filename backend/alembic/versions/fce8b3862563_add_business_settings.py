"""add_business_settings

Revision ID: fce8b3862563
Revises: 7a0603aab90e
Create Date: 2026-02-23 13:35:34.818055

"""
from typing import Sequence, Union
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fce8b3862563'
down_revision: Union[str, Sequence[str], None] = '7a0603aab90e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "business_settings",
        sa.Column("business_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("businesses.id"), primary_key=True),

        sa.Column("main_marketplace", sa.String(length=50), nullable=False, server_default="ebay.de"),

        sa.Column("default_shipping_cost", sa.Numeric(10, 2), nullable=False, server_default="6.00"),
        sa.Column("default_packaging_cost", sa.Numeric(10, 2), nullable=False, server_default="0.50"),

        sa.Column("ebay_fee_percent", sa.Numeric(5, 2), nullable=False, server_default="12.00"),
        sa.Column("promo_percent", sa.Numeric(5, 2), nullable=False, server_default="2.00"),
        sa.Column("target_profit", sa.Numeric(10, 2), nullable=False, server_default="5.00"),

        sa.Column("rounding_mode", sa.String(length=20), nullable=False, server_default="END_99"),

        sa.Column("demand_low_multiplier", sa.Numeric(5, 2), nullable=False, server_default="2.20"),
        sa.Column("demand_medium_multiplier", sa.Numeric(5, 2), nullable=False, server_default="2.60"),
        sa.Column("demand_high_multiplier", sa.Numeric(5, 2), nullable=False, server_default="3.20"),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("business_settings")
