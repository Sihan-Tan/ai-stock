"""AkShare 涨停池 → 情绪客户端（QMT 不可用时降级）。"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from desk_common.symbols import normalize_symbol

_LOGGER = logging.getLogger(__name__)


def _code_to_symbol(code: Any) -> str:
    """东财代码转规范 symbol。"""
    raw = str(code or "").strip()
    if not raw:
        return ""
    if "." in raw:
        return normalize_symbol(raw)
    if raw.startswith(("6", "9")):
        return normalize_symbol(f"{raw}.SH")
    return normalize_symbol(f"{raw}.SZ")


class FallbackSentimentClient:
    """主源为空时再试次源（如 xtdata → akshare）。"""

    def __init__(self, primary: Any, secondary: Any) -> None:
        self.primary = primary
        self.secondary = secondary

    def fetch_limit_performance(self, symbols: list[str], asof: date) -> list[dict[str, Any]]:
        """先主后备。"""
        try:
            rows = self.primary.fetch_limit_performance(symbols, asof)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("primary sentiment client failed: %s", exc)
            rows = []
        if rows:
            return rows
        try:
            return self.secondary.fetch_limit_performance(symbols, asof)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("secondary sentiment client failed: %s", exc)
            return []


class AkshareSentimentClient:
    """
    用东方财富涨停池（akshare）构造 limitupperformance 风格行。

    不依赖全市场 symbols 列表；``symbols`` 仅作可选过滤。
    """

    def fetch_limit_performance(self, symbols: list[str], asof: date) -> list[dict[str, Any]]:
        """
        拉取指定日涨停/跌停池。

        @param symbols: 可选宇宙；空则不过滤
        @param asof: 交易日
        """
        import akshare as ak

        day = asof.strftime("%Y%m%d")
        allow = {normalize_symbol(s) for s in symbols if s} if symbols else None
        out: list[dict[str, Any]] = []

        try:
            zt = ak.stock_zt_pool_em(date=day)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("akshare stock_zt_pool_em failed: %s", exc)
            zt = None

        if zt is not None and getattr(zt, "empty", True) is False:
            for _, row in zt.iterrows():
                sym = _code_to_symbol(row.get("代码") or row.get("code"))
                if not sym:
                    continue
                if allow is not None and sym not in allow:
                    continue
                try:
                    height = int(float(row.get("连板数") or row.get("连板高度") or 1))
                except (TypeError, ValueError):
                    height = 1
                try:
                    break_up = int(float(row.get("炸板次数") or 0))
                except (TypeError, ValueError):
                    break_up = 0
                try:
                    seal = float(row.get("封板资金") or row.get("封单资金") or 0)
                except (TypeError, ValueError):
                    seal = 0.0
                out.append(
                    {
                        "symbol": sym,
                        "name": str(row.get("名称") or row.get("name") or "").strip(),
                        "direct": 1,
                        "sealCount": max(1, height),
                        "breakUp": break_up,
                        "upAmount": seal,
                        "concept": str(row.get("所属行业") or row.get("概念") or "").strip(),
                    }
                )

        try:
            dt = ak.stock_zt_pool_dtgc_em(date=day)
        except Exception:  # noqa: BLE001
            try:
                dt = ak.stock_zt_pool_dt_em(date=day)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("akshare limit-down pool failed: %s", exc)
                dt = None

        if dt is not None and getattr(dt, "empty", True) is False:
            for _, row in dt.iterrows():
                sym = _code_to_symbol(row.get("代码") or row.get("code"))
                if not sym:
                    continue
                if allow is not None and sym not in allow:
                    continue
                out.append(
                    {
                        "symbol": sym,
                        "name": str(row.get("名称") or row.get("name") or "").strip(),
                        "direct": 2,
                        "sealCount": 1,
                        "breakUp": 0,
                        "upAmount": 0.0,
                        "concept": str(row.get("所属行业") or "").strip(),
                    }
                )

        return out
