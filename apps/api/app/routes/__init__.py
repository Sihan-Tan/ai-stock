"""路由聚合。"""

from fastapi import APIRouter

from app.routes import (
    alerts,
    ai,
    backtest,
    broker,
    calendar,
    factor_ml,
    knowledge,
    market,
    morning,
    review,
    sentiment_lhb,
    settings,
    strategies,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(market.router, tags=["market"])
api_router.include_router(calendar.router, tags=["calendar"])
api_router.include_router(sentiment_lhb.router, tags=["sentiment-lhb"])
api_router.include_router(strategies.router, tags=["strategies"])
api_router.include_router(backtest.router, tags=["backtest"])
api_router.include_router(broker.router, tags=["broker"])
api_router.include_router(alerts.router, tags=["alerts"])
api_router.include_router(factor_ml.router, tags=["factor-ml"])
api_router.include_router(ai.router, tags=["ai"])
api_router.include_router(morning.router, tags=["morning"])
api_router.include_router(review.router, tags=["review"])
api_router.include_router(knowledge.router, tags=["knowledge"])
api_router.include_router(settings.router, tags=["settings"])
