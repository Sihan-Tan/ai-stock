"""清空 desk 库全部表数据，并执行 alembic upgrade。"""

from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text

URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://desk:desk@127.0.0.1:5432/desk"
)


def truncate_all(url: str) -> None:
    """TRUNCATE 全部业务表。"""
    eng = create_engine(url, connect_args={"connect_timeout": 5})
    with eng.begin() as conn:
        tables = inspect(eng).get_table_names()
        if "bars_daily" in tables:
            n = conn.execute(text("SELECT count(*) FROM bars_daily")).scalar()
            print(f"before truncate: {len(tables)} tables, bars_daily={n}")
        for t in tables:
            conn.execute(text(f'TRUNCATE TABLE "{t}" RESTART IDENTITY CASCADE'))
        if "bars_daily" in tables:
            n = conn.execute(text("SELECT count(*) FROM bars_daily")).scalar()
            print(f"after truncate: bars_daily={n}")


def show_bars_daily(url: str) -> None:
    """打印 bars_daily 列。"""
    eng = create_engine(url, connect_args={"connect_timeout": 5})
    with eng.connect() as conn:
        cols = inspect(eng).get_columns("bars_daily")
        for col in cols:
            print(f"  {col['name']}: {col['type']}")
        if "alembic_version" in inspect(eng).get_table_names():
            print("alembic", conn.execute(text("SELECT * FROM alembic_version")).fetchall())


def main() -> int:
    """清空数据后跑迁移。"""
    os.environ["DATABASE_URL"] = URL
    truncate_all(URL)
    print("running alembic upgrade head ...")
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        check=False,
    )
    if r.returncode != 0:
        return r.returncode
    print("bars_daily columns after migrate:")
    show_bars_daily(URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
