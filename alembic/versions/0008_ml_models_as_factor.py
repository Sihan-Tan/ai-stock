"""ml_models 增加 as_factor。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_ml_models_as_factor"
down_revision: Union[str, None] = "0007_lhb_daily_pct_chg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ml_models",
        sa.Column("as_factor", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("ml_models", "as_factor")
