"""加宽 alerts.status，容纳飞书失败详情。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_alerts_status_width"
down_revision: Union[str, None] = "0008_ml_models_as_factor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "alerts",
        "status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=128),
        existing_nullable=False,
        existing_server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "alerts",
        "status",
        existing_type=sa.String(length=128),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default=None,
    )
