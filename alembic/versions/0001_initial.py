"""初始 schema。"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建全部业务表。"""
    from desk_db import Base
    import desk_db.models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """删除全部业务表。"""
    from desk_db import Base
    import desk_db.models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
