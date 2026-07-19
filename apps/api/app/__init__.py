"""FastAPI 应用入口。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import api_router
from desk_common.settings import get_settings
from desk_db import ping_db, try_ensure_schema
import desk_db.models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    启动服务：建表放到后台线程，不阻塞接受请求；数据库不可达时服务仍可用。
    """
    # 不 await：API 立刻 ready，建表失败只打日志
    schema_task = asyncio.create_task(asyncio.to_thread(try_ensure_schema))

    schedulers = []
    settings = get_settings()
    if settings.market_scheduler_enabled:
        from desk_market.scheduler import build_market_scheduler

        market_sched, _ = build_market_scheduler(enabled=True)
        market_sched.start()
        schedulers.append(market_sched)
    # Paper Runner 定时（受 PAPER_RUNNER_ENABLED 控制）
    try:
        from desk_broker.runner_scheduler import build_paper_runner_scheduler

        runner_sched, _ = build_paper_runner_scheduler()
        if runner_sched.get_jobs():
            runner_sched.start()
            schedulers.append(runner_sched)
    except Exception:  # noqa: BLE001
        logger.exception("paper runner scheduler failed to start")
    yield
    for sched in schedulers:
        try:
            sched.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
    if not schema_task.done():
        schema_task.cancel()
        try:
            await schema_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


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
        """进程健康；db=false 时前端提示数据库不可达。"""
        settings = get_settings()
        db_ok = ping_db()
        return {
            "ok": True,
            "db": db_ok,
            "db_detail": "ok" if db_ok else "unreachable",
            "trade_mode": settings.trade_mode,
            "ml_engine": settings.ml_engine,
            "llm_provider": settings.llm_provider,
        }

    return app


app = create_app()
