"""strategies 表增加生命周期 / KPI 字段。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_strategy_lifecycle"
down_revision: Union[str, None] = "0004_calendar_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "strategies",
        sa.Column("lifecycle_stage", sa.String(length=16), nullable=False, server_default="incubating"),
    )
    op.add_column(
        "strategies",
        sa.Column("description", sa.String(length=256), nullable=False, server_default=""),
    )
    op.add_column(
        "strategies",
        sa.Column("capital_pct", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "strategies",
        sa.Column("capital_allocated", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "strategies",
        sa.Column("kpi_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "strategies",
        sa.Column("lifecycle_history_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "strategies",
        sa.Column("lifecycle_updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategies", "lifecycle_updated_at")
    op.drop_column("strategies", "lifecycle_history_json")
    op.drop_column("strategies", "kpi_json")
    op.drop_column("strategies", "capital_allocated")
    op.drop_column("strategies", "capital_pct")
    op.drop_column("strategies", "description")
    op.drop_column("strategies", "lifecycle_stage")
