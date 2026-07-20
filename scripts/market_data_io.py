"""行情相关表导出/导入的共享定义与工具。"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import MetaData, String, Table, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool

from desk_common.settings import get_settings

# 核心行情表（方案 A）
MARKET_TABLES: tuple[str, ...] = (
    "bars_daily",
    "bars_minute",
    "quotes_snapshot",
    "security_meta",
    "trade_calendar",
)

MANIFEST_NAME = "manifest.json"


def create_cli_engine(url: str | None = None) -> Engine:
    """
    CLI 专用引擎：短连接超时、无 pool_pre_ping，避免库不可达时长时间阻塞。

    @param url: DATABASE_URL；None 时读 Settings
    """
    settings = get_settings()
    db_url = url or settings.database_url
    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
    else:
        connect_args["connect_timeout"] = int(settings.db_connect_timeout)
    return create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=False,
        poolclass=NullPool,
        future=True,
    )


def default_market_dir(repo_root: Path | None = None) -> Path:
    """默认导出目录：<repo>/data/market。"""
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "data" / "market"


def csv_path(out_dir: Path, table: str) -> Path:
    """表对应的 CSV 路径。"""
    return out_dir / f"{table}.csv"


def list_existing_tables(engine: Engine, names: tuple[str, ...] = MARKET_TABLES) -> list[str]:
    """返回库中实际存在的目标表名。"""
    present = set(inspect(engine).get_table_names())
    return [n for n in names if n in present]


def _json_safe(value: Any) -> Any:
    """将 date/datetime 转为 ISO 字符串，便于写入 manifest。"""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def export_tables(engine: Engine, out_dir: Path, tables: list[str] | None = None) -> dict[str, Any]:
    """
    导出表到 CSV，并写 manifest.json。

    @param engine: SQLAlchemy Engine
    @param out_dir: 输出目录
    @param tables: 表名列表；默认 MARKET_TABLES 中存在的表
    @return: manifest 内容
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    target = tables if tables is not None else list_existing_tables(engine)
    files: dict[str, Any] = {}
    with engine.connect() as conn:
        for name in target:
            df = pd.read_sql_query(text(f'SELECT * FROM "{name}"'), conn)
            path = csv_path(out_dir, name)
            df.to_csv(path, index=False, encoding="utf-8")
            files[name] = {
                "file": path.name,
                "rows": int(len(df)),
                "columns": list(df.columns),
            }
            print(f"export {name}: {len(df)} rows -> {path}")

    manifest = {
        "version": 1,
        "kind": "market",
        "tables": MARKET_TABLES,
        "exported_at": datetime.now(tz=None).isoformat(timespec="seconds") + "Z",
        "files": files,
    }
    manifest_path = out_dir / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_safe),
        encoding="utf-8",
    )
    print(f"wrote {manifest_path}")
    return manifest


def _load_table(engine: Engine, name: str) -> Table:
    """反射单表。"""
    meta = MetaData()
    return Table(name, meta, autoload_with=engine)


def _prepare_dataframe(df: pd.DataFrame, table: Table) -> pd.DataFrame:
    """按表列对齐，并把空字符串 / NaN 转成适合插入的值。"""
    cols = [c.name for c in table.columns]
    for col in cols:
        if col not in df.columns:
            df[col] = None
    out = df[cols].copy()
    out = out.astype(object)
    out = out.where(pd.notnull(out), None)
    out = out.replace({"": None})
    for col in out.columns:
        out[col] = out[col].apply(lambda v: None if isinstance(v, float) and pd.isna(v) else v)

    # NOT NULL 字符串列：None → 空串，避免 IntegrityError
    for column in table.columns:
        if column.name == "id":
            continue
        if column.nullable is False and isinstance(column.type, String):
            out[column.name] = out[column.name].apply(lambda v: "" if v is None else v)
    return out


def import_tables(
    engine: Engine,
    src_dir: Path,
    *,
    clear: bool = True,
    tables: list[str] | None = None,
) -> dict[str, int]:
    """
    从 CSV 导入行情表。

    @param engine: SQLAlchemy Engine
    @param src_dir: 含 CSV / manifest 的目录
    @param clear: True 时先清空目标表再插入
    @param tables: 限定表名；默认按 MARKET_TABLES 且文件存在
    @return: 各表导入行数
    """
    existing = set(list_existing_tables(engine))
    if tables is None:
        names = [n for n in MARKET_TABLES if csv_path(src_dir, n).exists() and n in existing]
    else:
        names = [n for n in tables if csv_path(src_dir, n).exists() and n in existing]

    date_cols = {
        "bars_daily": ["ts"],
        "bars_minute": ["ts"],
        "quotes_snapshot": ["updated_at"],
        "security_meta": ["updated_at"],
        "trade_calendar": ["cal_date"],
    }

    # 事务外反射，避免 sqlite :memory: 在 begin() 内另开连接丢数据
    reflected = {name: _load_table(engine, name) for name in names}

    counts: dict[str, int] = {}
    with engine.begin() as conn:
        for name in names:
            path = csv_path(src_dir, name)
            parse = date_cols.get(name) or None
            df = pd.read_csv(path, encoding="utf-8", parse_dates=parse)
            if "symbol" in df.columns:
                df["symbol"] = df["symbol"].astype(str)
            table = reflected[name]
            prepared = _prepare_dataframe(df, table)
            if clear:
                conn.execute(text(f'DELETE FROM "{name}"'))
            if prepared.empty:
                counts[name] = 0
                print(f"import {name}: 0 rows (clear={clear})")
                continue
            if "id" in prepared.columns:
                prepared = prepared.drop(columns=["id"])
            records = prepared.to_dict(orient="records")
            chunk = 1000
            for i in range(0, len(records), chunk):
                conn.execute(table.insert(), records[i : i + chunk])
            counts[name] = int(len(prepared))
            print(f"import {name}: {counts[name]} rows (clear={clear})")
    return counts
