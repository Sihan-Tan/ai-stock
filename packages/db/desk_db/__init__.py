"""数据库会话与引擎。"""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from desk_common.settings import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """ORM 基类。"""


def create_db_engine(url: str | None = None):
    """
    创建 SQLAlchemy Engine。

    非 SQLite 库使用短 connect_timeout，避免启动/探测长时间阻塞。
    """
    settings = get_settings()
    db_url = url or settings.database_url
    connect_args: dict = {}
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if db_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
        # 文件库用 NullPool，避免测试 drop_all 时连接占用；内存库用 StaticPool
        if ":memory:" in db_url or "mode=memory" in db_url:
            kwargs["poolclass"] = StaticPool
        else:
            kwargs["poolclass"] = NullPool
    else:
        # psycopg / PyMySQL：秒级连接超时
        connect_args["connect_timeout"] = int(settings.db_connect_timeout)
    return create_engine(db_url, connect_args=connect_args, **kwargs)


_engine = None
_SessionLocal = None


def get_engine():
    """惰性获取全局 Engine。"""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_db_engine()
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """获取 Session 工厂。"""
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级 Session。"""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ping_db() -> bool:
    """健康检查：能否连通数据库。"""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _ensure_sqlite_column(table: str, column: str, ddl_type: str = "VARCHAR(64)") -> None:
    """SQLite 已有表补列（表不存在则跳过）。"""
    engine = get_engine()
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchone()
        if not exists:
            return
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        names = {r[1] for r in rows}
        if column not in names:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def _ensure_position_strategy_columns() -> None:
    """已有库补列：paper/live_positions.strategy_id。"""
    engine = get_engine()
    dialect = engine.dialect.name
    if dialect == "sqlite":
        _ensure_sqlite_column("paper_positions", "strategy_id")
        _ensure_sqlite_column("live_positions", "strategy_id")
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(64)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE live_positions ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(64)"
            )
        )


def try_ensure_schema() -> bool:
    """
    尝试 create_all；失败只记日志，不抛出。

    @returns: 是否建表成功
    """
    try:
        Base.metadata.create_all(bind=get_engine())
        try:
            _ensure_position_strategy_columns()
        except Exception as exc:  # noqa: BLE001
            logger.warning("补齐 positions.strategy_id 失败：%s", exc)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("数据库不可达或建表失败，服务仍继续启动：%s", exc)
        return False


def reset_engine() -> None:
    """测试用：重置全局引擎。"""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
