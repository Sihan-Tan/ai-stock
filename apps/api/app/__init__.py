"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import api_router
from desk_common.settings import get_settings
from desk_db import Base, get_engine, ping_db
import desk_db.models  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时确保表存在，并按配置拉起行情调度器。"""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    scheduler = None
    settings = get_settings()
    if settings.market_scheduler_enabled:
        from desk_market.scheduler import build_market_scheduler

        scheduler, _ = build_market_scheduler(enabled=True)
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    """创建应用。"""
    app = FastAPI(title="刻度 Desk API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/health")
    def health():
        settings = get_settings()
        return {
            "ok": True,
            "db": ping_db(),
            "trade_mode": settings.trade_mode,
            "ml_engine": settings.ml_engine,
            "llm_provider": settings.llm_provider,
        }

    return app


app = create_app()
