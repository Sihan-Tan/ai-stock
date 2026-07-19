"""financial_snapshots 缓存表。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_financial_snapshots"
down_revision: Union[str, None] = "0005_strategy_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financial_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("table_name", sa.String(length=32), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "table_name", "period", name="uq_financial_snap"),
    )
    op.create_index("ix_financial_snapshots_symbol", "financial_snapshots", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_financial_snapshots_symbol", table_name="financial_snapshots")
    op.drop_table("financial_snapshots")
