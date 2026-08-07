"""research_picks / morning_strong_picks / closing_picks：strategy_id 与唯一约束。"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_research_history_upsert"
down_revision: Union[str, None] = "0011_auction_price"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dedupe_keep_max_id(table: str, group_cols: Sequence[str]) -> None:
    """按分组保留 MAX(id)，删除其余重复行（嵌套子查询兼容 SQLite）。"""
    cols = ", ".join(group_cols)
    op.execute(
        sa.text(
            f"""
            DELETE FROM {table}
            WHERE id NOT IN (
                SELECT mid FROM (
                    SELECT MAX(id) AS mid FROM {table} GROUP BY {cols}
                ) AS keepers
            )
            """
        )
    )


def upgrade() -> None:
    """增加可空 strategy_id、去重并建立唯一约束。"""
    # SQLite 不支持直接 ADD CONSTRAINT，统一用 batch（Postgres 仍为普通 ALTER）
    with op.batch_alter_table("research_picks") as batch_op:
        batch_op.add_column(sa.Column("strategy_id", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_research_picks_strategy_id", ["strategy_id"])

    _dedupe_keep_max_id("research_picks", ["asof", "source", "symbol"])

    with op.batch_alter_table("research_picks") as batch_op:
        batch_op.create_unique_constraint(
            "uq_research_picks_asof_source_symbol",
            ["asof", "source", "symbol"],
        )

    with op.batch_alter_table("morning_strong_picks") as batch_op:
        batch_op.add_column(sa.Column("strategy_id", sa.String(length=64), nullable=True))

    _dedupe_keep_max_id("morning_strong_picks", ["asof", "pick_type", "code"])

    with op.batch_alter_table("morning_strong_picks") as batch_op:
        batch_op.create_unique_constraint(
            "uq_morning_strong_asof_type_code",
            ["asof", "pick_type", "code"],
        )

    _dedupe_keep_max_id("closing_picks", ["asof", "strategy_id", "code"])

    with op.batch_alter_table("closing_picks") as batch_op:
        batch_op.create_unique_constraint(
            "uq_closing_picks_asof_strategy_code",
            ["asof", "strategy_id", "code"],
        )


def downgrade() -> None:
    """回滚唯一约束与 strategy_id 列。"""
    with op.batch_alter_table("closing_picks") as batch_op:
        batch_op.drop_constraint("uq_closing_picks_asof_strategy_code", type_="unique")

    with op.batch_alter_table("morning_strong_picks") as batch_op:
        batch_op.drop_constraint("uq_morning_strong_asof_type_code", type_="unique")
        batch_op.drop_column("strategy_id")

    with op.batch_alter_table("research_picks") as batch_op:
        batch_op.drop_constraint("uq_research_picks_asof_source_symbol", type_="unique")
        batch_op.drop_index("ix_research_picks_strategy_id")
        batch_op.drop_column("strategy_id")
