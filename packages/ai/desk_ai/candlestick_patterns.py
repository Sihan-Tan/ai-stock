"""投研用：TA-Lib K 线形态扫描。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

_LOOKBACK_DEFAULT = 30
_LOOKBACK_MIN = 5
_LOOKBACK_MAX = 120
_HITS_CAP = 80


def list_cdl_factor_names() -> list[str]:
    """注册表中全部 CDL 形态因子名（大写）。"""
    from desk_factor.registry import FACTOR_REGISTRY

    names: list[str] = []
    for f in FACTOR_REGISTRY:
        talib = str(f.get("talib") or "").upper()
        name = str(f.get("name") or "").upper()
        if talib.startswith("CDL") and name == talib and f.get("enabled", True):
            names.append(name)
    return names


def _zh_short(name: str) -> str:
    """中文短名：去掉「K线形态：」前缀。"""
    from desk_factor.zh_desc import TALIB_ZH_DESC

    desc = TALIB_ZH_DESC.get(name.upper(), "") or name
    if "：" in desc:
        return desc.split("：", 1)[-1]
    if ":" in desc:
        return desc.split(":", 1)[-1]
    return desc


def _build_alias_map(all_names: list[str]) -> dict[str, str]:
    """别名 → 标准 CDL 名。"""
    amap: dict[str, str] = {}
    for name in all_names:
        amap[name.upper()] = name
        amap[name.upper().removeprefix("CDL")] = name
        short = _zh_short(name)
        amap[short] = name
        amap[short.lower()] = name
    return amap


def resolve_pattern_names(patterns: list[str] | None) -> tuple[list[str], list[str]]:
    """解析用户指定的形态列表。

    Returns:
        ``(resolved_names, unknown)``；``patterns`` 空则 resolved=全部 CDL。
    """
    all_names = list_cdl_factor_names()
    if not patterns:
        return all_names, []
    amap = _build_alias_map(all_names)
    resolved: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in patterns:
        key = str(raw or "").strip()
        if not key:
            continue
        name = amap.get(key) or amap.get(key.upper()) or amap.get(key.lower())
        if name is None:
            unknown.append(key)
            continue
        if name not in seen:
            seen.add(name)
            resolved.append(name)
    return resolved, unknown


def get_candlestick_patterns(
    db: Session,
    symbol: str,
    *,
    lookback_bars: int = _LOOKBACK_DEFAULT,
    patterns: list[str] | None = None,
    only_hits: bool = True,
) -> dict[str, Any]:
    """扫描标的近 N 根日线的 TA-Lib CDL 形态。

    Args:
        db: 数据库 Session。
        symbol: 股票代码。
        lookback_bars: 可见窗口 bar 数。
        patterns: 筛选形态；空=全部。
        only_hits: True 时只返回非 0 信号。

    Returns:
        命中结果或 ``error`` 字典。
    """
    from desk_factor import FactorService
    from desk_common.symbols import normalize_symbol
    from desk_indicators import HAS_TALIB

    if not HAS_TALIB:
        return {
            "error": "未安装 TA-Lib（可选依赖），无法计算 K 线形态。请安装 TA-Lib 后重试。",
            "engine": "python",
        }

    sym = normalize_symbol(str(symbol or "").strip())
    if not sym:
        return {"error": "symbol 不能为空"}

    lb = int(lookback_bars or _LOOKBACK_DEFAULT)
    lb = max(_LOOKBACK_MIN, min(_LOOKBACK_MAX, lb))

    resolved, unknown = resolve_pattern_names(patterns)
    if unknown and not resolved:
        return {"error": f"未知形态: {', '.join(unknown)}", "unknown": unknown}
    if not resolved:
        return {"error": "无可用 CDL 形态"}

    end = date.today()
    # 日历缓冲：窗口 + 预热；具体预热由 FactorService.compute_series 再扩
    start = end - timedelta(days=max(lb * 3, 90))

    try:
        out = FactorService(db).compute_series(sym, resolved, start=start, end=end)
    except ValueError as exc:
        return {"error": str(exc), "symbol": sym}

    bars = list(out.get("bars") or [])
    if not bars:
        return {"error": "无本地日线", "symbol": sym}

    window = bars[-lb:]
    date_set = {str(b.get("date", ""))[:10] for b in window}
    engine = out.get("engine") or ("talib" if HAS_TALIB else "python")

    hits: list[dict[str, Any]] = []
    series = out.get("series") or {}
    for name in resolved:
        block = series.get(name) or series.get(name.upper()) or {}
        outputs = block.get("outputs") or {}
        # CDL 通常单输出列，取第一个
        points: list[dict[str, Any]] = []
        for _col, pts in outputs.items():
            points = pts or []
            break
        zh = _zh_short(name)
        for p in points:
            d = str(p.get("date", ""))[:10]
            if d not in date_set:
                continue
            v = p.get("v")
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if only_hits and fv == 0.0:
                continue
            hits.append(
                {
                    "date": d,
                    "name": name,
                    "name_zh": zh,
                    "value": int(fv) if fv == int(fv) else fv,
                }
            )

    hits.sort(key=lambda h: (h["date"], h["name"]), reverse=True)
    truncated = len(hits) > _HITS_CAP
    if truncated:
        hits = hits[:_HITS_CAP]

    note = "value>0 偏多信号，value<0 偏空（TA-Lib 惯例）；形态识别主观，需结合知识库与其它工具。"
    if unknown:
        note += f" 已忽略未知形态: {', '.join(unknown)}。"
    if truncated:
        note += f" 命中超过 {_HITS_CAP} 条已截断。"

    return {
        "symbol": sym,
        "engine": engine,
        "lookback_bars": lb,
        "patterns_used": resolved,
        "pattern_count": len(resolved),
        "window_start": str(window[0].get("date", ""))[:10] if window else None,
        "window_end": str(window[-1].get("date", ""))[:10] if window else None,
        "hits": hits,
        "hit_count": len(hits),
        "only_hits": only_hits,
        "note": note,
    }
