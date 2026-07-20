"""导出行情相关表到 data/market/*.csv。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from market_data_io import (  # noqa: E402
    create_cli_engine,
    default_market_dir,
    export_tables,
    list_existing_tables,
)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="导出核心行情表到 CSV（bars/quotes/meta/calendar）")
    parser.add_argument(
        "--url",
        default=None,
        help="DATABASE_URL；默认读 Settings / .env",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出目录（默认 data/market）",
    )
    args = parser.parse_args(argv)

    out_dir = args.out or default_market_dir(_REPO)
    engine = create_cli_engine(args.url)
    try:
        tables = list_existing_tables(engine)
        if not tables:
            print("没有可导出的行情表（库中不存在目标表）", file=sys.stderr)
            return 1
        export_tables(engine, out_dir, tables)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
