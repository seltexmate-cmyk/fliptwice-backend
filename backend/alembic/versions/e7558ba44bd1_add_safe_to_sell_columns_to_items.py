"""add safe_to_sell columns to items

Revision ID: e7558ba44bd1
Revises: fce8b3862563
Create Date: 2026-02-24 16:07:13.330034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e7558ba44bd1'
down_revision: Union[str, Sequence[str], None] = 'fce8b3862563'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("items")}

    if "safe_to_sell" not in cols:
        op.add_column("items", sa.Column("safe_to_sell", sa.Boolean(), nullable=True))

    if "safe_to_sell_reasons" not in cols:
        op.add_column(
            "items",
            sa.Column("safe_to_sell_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("items")}

    if "safe_to_sell_reasons" in cols:
        op.drop_column("items", "safe_to_sell_reasons")

    if "safe_to_sell" in cols:
        op.drop_column("items", "safe_to_sell")