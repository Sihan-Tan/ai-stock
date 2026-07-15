"""补齐 bars_daily 后复权列，价格列改为 Numeric(18,3)。"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_bars_price_hfq_numeric"
down_revision: Union[str, None] = "0002_bars_daily_hfq_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRICE = sa.Numeric(18, 3)

_HFQ_PRICE_COLUMNS = (
    "open_hfq",
    "high_hfq",
    "low_hfq",
    "close_hfq",
)

_DAILY_PRICE_COLUMNS = ("open", "high", "low", "close")
_MINUTE_PRICE_COLUMNS = ("open", "high", "low", "close")


def _pg_alter_column_numeric(table: str, column: str, nullable: bool = False) -> None:
    """PostgreSQL：将列改为 NUMERIC(18,3)。"""
    op.execute(
        sa.text(
            f'ALTER TABLE {table} ALTER COLUMN "{column}" TYPE NUMERIC(18,3) '
            f'USING round("{column}"::numeric, 3)'
        )
    )
    if not nullable:
        op.execute(sa.text(f'ALTER TABLE {table} ALTER COLUMN "{column}" SET NOT NULL'))


def upgrade() -> None:
    """增加缺失的后复权价格列，并将 OHLC 改为三位小数 Numeric。"""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    dialect = bind.dialect.name

    if "bars_daily" in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns("bars_daily")}
        with op.batch_alter_table("bars_daily") as batch_op:
            for name in _HFQ_PRICE_COLUMNS:
                if name not in existing:
                    batch_op.add_column(sa.Column(name, _PRICE, nullable=True))
            if "volume_hfq" not in existing:
                batch_op.add_column(sa.Column("volume_hfq", sa.Float(), nullable=True))

        if dialect == "postgresql":
            for name in _DAILY_PRICE_COLUMNS:
                _pg_alter_column_numeric("bars_daily", name, nullable=False)
            for name in _HFQ_PRICE_COLUMNS:
                _pg_alter_column_numeric("bars_daily", name, nullable=True)
        elif dialect == "sqlite":
            # SQLite 类型亲和，batch recreate；create_all 路径已用新 ORM 类型
            pass

    if "bars_minute" in insp.get_table_names() and dialect == "postgresql":
        for name in _MINUTE_PRICE_COLUMNS:
            _pg_alter_column_numeric("bars_minute", name, nullable=False)

    if "quotes_snapshot" in insp.get_table_names() and dialect == "postgresql":
        _pg_alter_column_numeric("quotes_snapshot", "last", nullable=False)


def downgrade() -> None:
    """回滚为 Float（PostgreSQL）。"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, cols in (
        ("bars_daily", list(_DAILY_PRICE_COLUMNS) + list(_HFQ_PRICE_COLUMNS)),
        ("bars_minute", list(_MINUTE_PRICE_COLUMNS)),
        ("quotes_snapshot", ["last"]),
    ):
        for name in cols:
            op.execute(sa.text(f'ALTER TABLE {table} ALTER COLUMN "{name}" TYPE DOUBLE PRECISION'))
