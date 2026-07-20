"""从 data/market/*.csv 导入行情相关表。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from market_data_io import (  # noqa: E402
    MANIFEST_NAME,
    create_cli_engine,
    default_market_dir,
    import_tables,
)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="从 CSV 导入核心行情表")
    parser.add_argument(
        "--url",
        default=None,
        help="DATABASE_URL；默认读 Settings / .env",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="CSV 目录（默认 data/market）",
    )
    parser.add_argument(
        "--clear",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="导入前清空目标表（默认开启；可用 --no-clear 关闭）",
    )
    args = parser.parse_args(argv)

    src = args.dir or default_market_dir(_REPO)
    if not src.is_dir():
        print(f"目录不存在: {src}", file=sys.stderr)
        return 1
    if not any(src.glob("*.csv")):
        print(f"目录中无 CSV: {src}", file=sys.stderr)
        return 1

    engine = create_cli_engine(args.url)
    try:
        counts = import_tables(engine, src, clear=args.clear)
        if not counts:
            print("没有导入任何表（缺文件或库中无对应表）", file=sys.stderr)
            return 1
        manifest = src / MANIFEST_NAME
        if manifest.exists():
            print(f"source manifest: {manifest}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
