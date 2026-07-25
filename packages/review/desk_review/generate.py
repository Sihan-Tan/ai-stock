"""LLM 日终复盘：预取事实 + 一次无工具生成。"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from desk_common.settings import get_settings

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")

LlmFn = Callable[[str, str], str]


def _parse_review_payload(text: str) -> dict[str, Any] | None:
    """从模型输出解析 content + deviations。"""
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    content = str(obj.get("content") or "").strip()
    if not content:
        return None
    deviations = obj.get("deviations")
    if not isinstance(deviations, list):
        deviations = []
    clean_dev: list[dict[str, Any]] = []
    for d in deviations:
        if isinstance(d, dict):
            clean_dev.append(d)
    return {"content": content, "deviations": clean_dev}


def _index_meta() -> list[dict[str, str]]:
    """指数 symbol + 名称。"""
    from desk_common.settings import get_settings
    from desk_common.symbols import normalize_symbol
    import yaml

    settings = get_settings()
    path = Path(settings.market_indices_yaml)
    if not path.is_file():
        path = Path(__file__).resolve().parents[3] / settings.market_indices_yaml
    if not path.is_file():
        return [
            {"symbol": "000001.SH", "name": "上证综指"},
            {"symbol": "000300.SH", "name": "沪深300"},
            {"symbol": "399006.SZ", "name": "创业板指"},
        ]
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[dict[str, str]] = []
    for item in raw.get("indices") or []:
        if not isinstance(item, dict) or not item.get("symbol"):
            continue
        out.append(
            {
                "symbol": normalize_symbol(str(item["symbol"])),
                "name": str(item.get("name") or item["symbol"]),
            }
        )
    return out


def prefetch_review_facts(
    db: Session,
    asof: date,
    *,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    """组装复盘预取事实（大盘 / 情绪 / 执行 / 归因）。"""
    from desk_broker.execution_quality import analyze_paper_execution
    from desk_market import MarketService
    from desk_review.attribution import simple_vs_buyhold
    from desk_sentiment import SentimentService

    market: list[dict[str, Any]] = []
    ms = MarketService(db)
    start = asof - timedelta(days=14)
    for meta in _index_meta():
        sym = meta["symbol"]
        try:
            df = ms.load_daily_df(sym, start, asof)
        except Exception:  # noqa: BLE001
            df = None
        if df is None or df.empty:
            market.append({"symbol": sym, "name": meta["name"], "error": "无日线"})
            continue
        # 取 asof 当日或之前最近一根
        df = df.copy()
        df["date"] = df["date"].astype(str).str[:10]
        day_rows = df[df["date"] <= asof.isoformat()]
        if day_rows.empty:
            market.append({"symbol": sym, "name": meta["name"], "error": "无日线"})
            continue
        last = day_rows.iloc[-1]
        prev = day_rows.iloc[-2] if len(day_rows) >= 2 else None
        close = float(last["close"])
        chg_pct = None
        if prev is not None and float(prev["close"]):
            chg_pct = (close / float(prev["close"]) - 1.0) * 100.0
        market.append(
            {
                "symbol": sym,
                "name": meta["name"],
                "date": str(last["date"])[:10],
                "close": close,
                "chg_pct": None if chg_pct is None else round(chg_pct, 2),
            }
        )

    try:
        sentiment = SentimentService(db).snapshot(asof)
    except Exception as exc:  # noqa: BLE001
        sentiment = {"error": str(exc)}

    exec_q = analyze_paper_execution(db, limit=80)
    # 压缩：只留当日或摘要指标
    asof_s = asof.isoformat()
    day_trades = [
        {
            "symbol": it.get("symbol"),
            "side": it.get("side"),
            "qty": it.get("qty"),
            "price": it.get("price"),
            "slip_bps": it.get("slip_bps"),
        }
        for it in (exec_q.get("items") or [])
        if str(it.get("created_at") or "")[:10] == asof_s
        or (it.get("created_at") and str(it["created_at"])[:10] == asof_s)
    ]
    execution = {
        "trades": exec_q.get("trades"),
        "avg_slip_bps": exec_q.get("avg_slip_bps"),
        "median_slip_bps": exec_q.get("median_slip_bps"),
        "buy_count": exec_q.get("buy_count"),
        "sell_count": exec_q.get("sell_count"),
        "asof_trades": day_trades[:20],
        "message": exec_q.get("message"),
    }

    try:
        attribution = simple_vs_buyhold(db, strategy_id=strategy_id)
    except Exception as exc:  # noqa: BLE001
        attribution = {"status": "error", "message": str(exc)}

    return {
        "asof": asof.isoformat(),
        "market": market,
        "sentiment": {
            "asof": sentiment.get("asof") if isinstance(sentiment, dict) else None,
            "limit_up_count": sentiment.get("limit_up_count") if isinstance(sentiment, dict) else None,
            "limit_down_count": sentiment.get("limit_down_count") if isinstance(sentiment, dict) else None,
            "max_board": sentiment.get("max_board") if isinstance(sentiment, dict) else None,
            "promote_rate": sentiment.get("promote_rate") if isinstance(sentiment, dict) else None,
            "break_rate": sentiment.get("break_rate") if isinstance(sentiment, dict) else None,
            "error": sentiment.get("error") if isinstance(sentiment, dict) else None,
        },
        "execution": execution,
        "attribution": attribution,
    }


def _default_llm_call(system: str, user: str) -> str:
    """同步调用 OpenAI 兼容 Chat。"""
    from openai import OpenAI

    from desk_ai.session import resolve_llm_model

    settings = get_settings()
    if not settings.llm_api_key:
        raise ValueError("未配置 LLM API Key")
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url or None)
    model = resolve_llm_model(settings.llm_provider, settings.llm_model)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return str(getattr(resp.choices[0].message, "content", None) or "")


def generate_review(
    db: Session,
    asof: date,
    *,
    strategy_id: str | None = None,
    force: bool = False,
    llm_call: LlmFn | None = None,
) -> dict[str, Any]:
    """生成并写入当日复盘。

    Args:
        db: Session。
        asof: 业务日。
        strategy_id: 归因策略，可选。
        force: True 时覆盖已有笔记；False 且已有则跳过。
        llm_call: 可注入的 (system, user) -> text。

    Returns:
        含 status/skipped/asof/content/deviations/facts 摘要。
    """
    from desk_review import ReviewService

    existing = ReviewService(db).get(asof)
    if existing and not force:
        return {
            "status": "skipped",
            "reason": "already_exists",
            "asof": asof.isoformat(),
            "content": existing.get("content"),
            "deviations": existing.get("deviations") or [],
        }

    settings = get_settings()
    if not settings.llm_api_key and llm_call is None:
        return {"status": "error", "error": "未配置 LLM API Key", "asof": asof.isoformat()}

    facts = prefetch_review_facts(db, asof, strategy_id=strategy_id)
    system = (
        "你是刻度 Desk 日终复盘助手。"
        "根据预取事实写复盘，禁止编造未给出的数字与成交。"
        "必须覆盖：大盘指数、情绪（若有）、当日/近期纸交易执行、策略归因要点。"
        "只输出一个 JSON 对象，不要其它文字。"
    )
    user = (
        f"业务日={asof.isoformat()}。预取事实：\n"
        f"{json.dumps(facts, ensure_ascii=False, default=str)}\n\n"
        "输出 JSON 字段：\n"
        '{"content":"Markdown 复盘正文（含 ## 大盘 ## 情绪 ## 交易执行 ## 策略归因 ## 小结）",'
        '"deviations":[{"type":"string","summary":"string","severity":"low|medium|high"}]}\n'
        "deviations 写可改进偏差；若无明显偏差可给空数组。"
        '请在 deviations 中加入 {"type":"llm","summary":"auto"} 标记来源。'
    )

    call = llm_call or _default_llm_call
    try:
        raw = call(system, user)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM review failed asof=%s", asof)
        return {"status": "error", "error": str(exc), "asof": asof.isoformat()}

    parsed = _parse_review_payload(raw)
    if not parsed:
        return {
            "status": "error",
            "error": "模型输出无法解析为 JSON",
            "asof": asof.isoformat(),
            "raw_preview": (raw or "")[:500],
        }

    deviations = list(parsed["deviations"])
    if not any(isinstance(d, dict) and d.get("type") == "llm" for d in deviations):
        deviations.insert(0, {"type": "llm", "summary": "auto" if not force else "manual"})

    saved = ReviewService(db).upsert(asof, parsed["content"], deviations)
    return {
        "status": "ok",
        "asof": saved["asof"],
        "content": saved["content"],
        "deviations": saved["deviations"],
        "facts": {
            "market": facts.get("market"),
            "sentiment": facts.get("sentiment"),
            "execution_trades": (facts.get("execution") or {}).get("trades"),
            "attribution_status": (facts.get("attribution") or {}).get("status"),
        },
    }


def maybe_auto_review(db: Session, asof: date | None = None) -> dict[str, Any] | None:
    """若 REVIEW_AUTO 开启则生成当日复盘（已有则跳过）。"""
    settings = get_settings()
    if not settings.review_auto:
        return None
    day = asof or date.today()
    try:
        return generate_review(db, day, force=False)
    except Exception:  # noqa: BLE001
        logger.exception("maybe_auto_review failed asof=%s", day)
        return {"status": "error", "error": "maybe_auto_review failed", "asof": day.isoformat()}
