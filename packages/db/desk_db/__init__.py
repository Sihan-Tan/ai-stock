"""数据库会话与引擎。"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from desk_common.settings import get_settings


class Base(DeclarativeBase):
    """ORM 基类。"""


def create_db_engine(url: str | None = None):
    """创建 SQLAlchemy Engine。"""
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


def reset_engine() -> None:
    """测试用：重置全局引擎。"""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
