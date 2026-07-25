"""auction_snapshots 增加竞价现价 auction_price。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_auction_price"
down_revision: Union[str, None] = "0010_research_picks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auction_snapshots",
        sa.Column("auction_price", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auction_snapshots", "auction_price")
