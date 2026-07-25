"""research_picks 投研精选落库表。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_research_picks"
down_revision: Union[str, None] = "0009_alerts_status_width"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_picks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asof", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_picks_asof", "research_picks", ["asof"])
    op.create_index("ix_research_picks_source", "research_picks", ["source"])
    op.create_index("ix_research_picks_symbol", "research_picks", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_research_picks_symbol", table_name="research_picks")
    op.drop_index("ix_research_picks_source", table_name="research_picks")
    op.drop_index("ix_research_picks_asof", table_name="research_picks")
    op.drop_table("research_picks")
