"""lhb_daily 增加上榜日涨跌幅 pct_chg。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_lhb_daily_pct_chg"
down_revision: Union[str, None] = "0006_financial_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lhb_daily", sa.Column("pct_chg", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("lhb_daily", "pct_chg")
