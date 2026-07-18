"""新增 calendar_events：财经日历 / 新闻 / 催化剂。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_calendar_events"
down_revision: Union[str, None] = "0003_bars_price_hfq_numeric"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="macro"),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("symbol", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("region", sa.String(length=16), nullable=False, server_default="CN"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="seed"),
        sa.Column("external_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_calendar_events_source_ext"),
    )
    op.create_index("ix_calendar_events_event_date", "calendar_events", ["event_date"])
    op.create_index("ix_calendar_events_category", "calendar_events", ["category"])


def downgrade() -> None:
    op.drop_index("ix_calendar_events_category", table_name="calendar_events")
    op.drop_index("ix_calendar_events_event_date", table_name="calendar_events")
    op.drop_table("calendar_events")
