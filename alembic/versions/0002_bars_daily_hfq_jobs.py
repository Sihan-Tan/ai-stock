"""BarDaily 后复权列 + SecurityMeta + MarketJobRun。"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_bars_daily_hfq_jobs"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HFQ_COLUMNS = (
    ("open_hfq", sa.Float()),
    ("high_hfq", sa.Float()),
    ("low_hfq", sa.Float()),
    ("close_hfq", sa.Float()),
    ("volume_hfq", sa.Float()),
)


def upgrade() -> None:
    """为 bars_daily 增加后复权列，并创建 security_meta / market_job_runs。"""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "bars_daily" in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns("bars_daily")}
        with op.batch_alter_table("bars_daily") as batch_op:
            for name, col_type in _HFQ_COLUMNS:
                if name not in existing:
                    batch_op.add_column(sa.Column(name, col_type, nullable=True))

    if "security_meta" not in insp.get_table_names():
        op.create_table(
            "security_meta",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("symbol", sa.String(length=16), nullable=False),
            sa.Column("name", sa.String(length=64), server_default="", nullable=False),
            sa.Column("is_delisted", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("status", sa.String(length=32), server_default="listed", nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("symbol", name="uq_security_meta_symbol"),
        )
        op.create_index(op.f("ix_security_meta_symbol"), "security_meta", ["symbol"], unique=False)

    if "market_job_runs" not in insp.get_table_names():
        op.create_table(
            "market_job_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("job_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("symbols_done", sa.Integer(), server_default="0", nullable=False),
            sa.Column("error_summary", sa.Text(), server_default="", nullable=False),
            sa.Column("message", sa.Text(), server_default="", nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_market_job_runs_job_id"), "market_job_runs", ["job_id"], unique=False)


def downgrade() -> None:
    """回滚后复权列与新表。"""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "market_job_runs" in insp.get_table_names():
        op.drop_index(op.f("ix_market_job_runs_job_id"), table_name="market_job_runs")
        op.drop_table("market_job_runs")

    if "security_meta" in insp.get_table_names():
        op.drop_index(op.f("ix_security_meta_symbol"), table_name="security_meta")
        op.drop_table("security_meta")

    if "bars_daily" in insp.get_table_names():
        existing = {c["name"] for c in insp.get_columns("bars_daily")}
        with op.batch_alter_table("bars_daily") as batch_op:
            for name, _ in reversed(_HFQ_COLUMNS):
                if name in existing:
                    batch_op.drop_column(name)
