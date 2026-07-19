"""为已有 PostgreSQL strategies 表补齐生命周期字段。"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from desk_common.settings import get_settings


def main() -> None:
    """执行 ALTER TABLE（列已存在则跳过）。"""
    url = get_settings().database_url
    engine = create_engine(url, connect_args={"connect_timeout": 8})
    needed = [
        ("lifecycle_stage", "VARCHAR(16) NOT NULL DEFAULT 'incubating'"),
        ("description", "VARCHAR(256) NOT NULL DEFAULT ''"),
        ("capital_pct", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("capital_allocated", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("kpi_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("lifecycle_history_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("lifecycle_updated_at", "TIMESTAMP NULL"),
    ]
    with engine.begin() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'strategies'"
                )
            )
        }
        print("before", sorted(cols))
        for name, ddl in needed:
            if name in cols:
                print("exists", name)
                continue
            conn.execute(text(f"ALTER TABLE strategies ADD COLUMN {name} {ddl}"))
            print("added", name)
        total = conn.execute(text("SELECT count(*) FROM strategies")).scalar()
        print("strategies_count", total)


if __name__ == "__main__":
    main()
