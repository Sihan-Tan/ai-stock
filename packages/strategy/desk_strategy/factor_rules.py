"""因子规则策略求值（kind: factor_rules）。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from desk_common.contracts import Side, Signal
from desk_factor.registry import get_factor
from desk_indicators import apply_factor_specs

COMPARE_OPS = frozenset({"gt", "gte", "lt", "lte", "eq"})
CROSS_OPS = frozenset({"cross_up", "cross_down"})
NEAR_OPS = frozenset({"near_pct"})
ALL_OPS = COMPARE_OPS | CROSS_OPS | NEAR_OPS
_ML_PREFIX = "ml:"
# 价格伪因子 → OHLCV 列名（不走 TA-Lib）
_PRICE_FACTOR_COLS: dict[str, str] = {
    "CLOSE": "close",
    "OPEN": "open",
    "HIGH": "high",
    "LOW": "low",
    "VOLUME": "volume",
}
_DEFAULT_NEAR_PCT = 3.0
_DEFAULT_WITHIN_BARS = 5


def _parse_within_bars(block: dict[str, Any]) -> int:
    """侧级 within_bars；非法/缺失 → 默认 5。"""
    raw = block.get("within_bars")
    if raw is None or raw == "":
        return _DEFAULT_WITHIN_BARS
    v = _as_float(raw)
    if v is None or v < 0 or int(v) != v:
        return _DEFAULT_WITHIN_BARS
    return int(v)


def _as_float(value: Any) -> float | None:
    """转为有限浮点；无效则 None。"""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if isinstance(out, float) and (np.isnan(out) or np.isinf(out)):
        return None
    return out


def collect_factor_names(data: dict[str, Any]) -> list[str]:
    """从 buy/sell 条件收集因子名（去重保序）。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for side_key in ("buy", "sell"):
        block = data.get(side_key) or {}
        for cond in block.get("conditions") or []:
            if not isinstance(cond, dict):
                continue
            for side in ("left", "right"):
                operand = cond.get(side)
                if not isinstance(operand, dict):
                    continue
                name = operand.get("factor")
                if isinstance(name, str) and name.strip():
                    key = name.strip()
                    if key not in seen:
                        seen.add(key)
                        ordered.append(key)
    return ordered


def _primary_output(factor_name: str) -> str | None:
    """因子主输出列名；ml: / 价格伪因子列名即约定名。"""
    key = factor_name.strip()
    if key.startswith(_ML_PREFIX):
        return key
    price_col = _PRICE_FACTOR_COLS.get(key.upper())
    if price_col is not None:
        return price_col
    meta = get_factor(key)
    if meta is None:
        return None
    outs = meta.get("outputs") or []
    if not outs:
        return None
    return str(outs[0])


def attach_ml_factor_columns(
    history: pd.DataFrame,
    factor_names: list[str],
    db: Any = None,
) -> pd.DataFrame:
    """
    将缺失的 ml: 打分列写入 history（按 date 对齐）。

    列已存在或 db 为空则跳过对应名；未 as_factor / 解析失败则跳过不抛错。

    @param history OHLCV 历史
    @param factor_names 因子名列表（可含非 ml:）
    @param db 可选 SQLAlchemy Session
    @returns 可能带 ml: 列的 DataFrame（可能为原对象或 copy）
    """
    if history is None or getattr(history, "empty", True):
        return history
    ml_names = [str(n) for n in factor_names if str(n).startswith(_ML_PREFIX)]
    missing = [n for n in ml_names if n not in history.columns]
    if not missing or db is None:
        return history

    from desk_factor import FactorService

    out = history.copy()
    svc = FactorService(db)
    for name in missing:
        try:
            row = svc._resolve_ml_model(name)
            packed = svc._ml_score_series(out, name, row)
        except Exception:  # noqa: BLE001
            continue
        points = (packed.get("outputs") or {}).get("ml_score") or []
        by_date = {str(p["date"])[:10]: p.get("v") for p in points}
        dates = out["date"].map(lambda d: str(d)[:10])
        out[name] = [by_date.get(d) for d in dates]
    return out


def enrich_history_with_factors(
    history: pd.DataFrame,
    factor_names: list[str],
    db: Any = None,
) -> pd.DataFrame:
    """
    在 OHLCV history 上计算所需因子列（TA + 缺失 ml:）。

    未知因子名跳过；不抛错。

    @param history OHLCV 历史
    @param factor_names 因子名列表
    @param db 可选 Session，供 ml: 打分
    """
    if history is None or getattr(history, "empty", True):
        return history
    out = attach_ml_factor_columns(history, factor_names, db)
    # 保证列名小写 OHLCV（CLOSE 等伪因子依赖 close 列）
    rename = {}
    for col in list(out.columns):
        low = str(col).lower()
        if low in {"open", "high", "low", "close", "volume"} and col != low:
            rename[col] = low
    if rename:
        out = out.rename(columns=rename)

    ta_names = [
        n
        for n in factor_names
        if not str(n).startswith(_ML_PREFIX)
        and str(n).strip().upper() not in _PRICE_FACTOR_COLS
    ]
    specs: list[dict[str, Any]] = []
    for raw in ta_names:
        meta = get_factor(raw)
        if meta is None:
            continue
        talib_name = str(meta.get("talib") or "").strip()
        if not talib_name:
            continue
        specs.append(
            {
                "talib": talib_name,
                "params": dict(meta.get("params") or {}),
                "outputs": list(meta.get("outputs") or []),
            }
        )
    if not specs:
        return out
    return apply_factor_specs(out, specs)


def _parse_lag(operand: dict[str, Any]) -> int:
    """操作数 lag（交易日）；非法/缺失 → 0。"""
    raw = operand.get("lag")
    if raw is None or raw == "":
        return 0
    v = _as_float(raw)
    if v is None or v < 0 or int(v) != v:
        return 0
    return int(v)


def _resolve_operand_at(
    operand: Any,
    enriched: pd.DataFrame,
    bar_i: int,
    *,
    cross_prev: bool = False,
) -> float | None:
    """
    在 bar_i 上解析操作数；因子支持 lag（再往前推 N 根）。

    cross_prev=True 时再额外往前 1 根（交叉用前一日）。
    """
    if not isinstance(operand, dict):
        return None
    if "const" in operand:
        return _as_float(operand.get("const"))
    name = operand.get("factor")
    if not isinstance(name, str) or not name.strip():
        return None
    col = _primary_output(name.strip())
    if col is None:
        return None
    lag = _parse_lag(operand)
    extra = 1 if cross_prev else 0
    target = bar_i - extra - lag
    if target < 0 or target >= len(enriched):
        return None
    row = enriched.iloc[target]
    if col not in row.index:
        col_l = col.lower()
        if col_l in row.index:
            col = col_l
        else:
            return None
    return _as_float(row.get(col))


def eval_condition(cond: dict[str, Any], enriched: pd.DataFrame, bar_i: int) -> bool:
    """
    在指定 bar 上求单条条件。

    未知因子 / 缺值 / lag 越界 → False。
    比较类：left 与 right×mult（mult 默认 1；≤0 则假）。
    交叉 / near_pct：可读操作数 lag，不读 mult。
    """
    op = str(cond.get("op") or "").strip().lower()
    if op not in ALL_OPS:
        return False
    left = cond.get("left")
    right = cond.get("right")
    if op in CROSS_OPS:
        if bar_i < 1:
            return False
        l0 = _resolve_operand_at(left, enriched, bar_i, cross_prev=False)
        r0 = _resolve_operand_at(right, enriched, bar_i, cross_prev=False)
        l1 = _resolve_operand_at(left, enriched, bar_i, cross_prev=True)
        r1 = _resolve_operand_at(right, enriched, bar_i, cross_prev=True)
        if None in (l0, r0, l1, r1):
            return False
        if op == "cross_up":
            return l1 <= r1 and l0 > r0
        return l1 >= r1 and l0 < r0

    if op == "near_pct":
        lv = _resolve_operand_at(left, enriched, bar_i)
        rv = _resolve_operand_at(right, enriched, bar_i)
        pct = _as_float(cond.get("pct"))
        if pct is None:
            pct = _DEFAULT_NEAR_PCT
        if lv is None or rv is None or rv == 0 or pct < 0:
            return False
        return abs(lv / rv - 1.0) * 100.0 <= pct

    lv = _resolve_operand_at(left, enriched, bar_i)
    rv = _resolve_operand_at(right, enriched, bar_i)
    if lv is None or rv is None:
        return False
    mult = _as_float(cond.get("mult"))
    if mult is None:
        mult = 1.0
    if mult <= 0:
        return False
    rv_eff = rv * mult
    if op == "gt":
        return lv > rv_eff
    if op == "gte":
        return lv >= rv_eff
    if op == "lt":
        return lv < rv_eff
    if op == "lte":
        return lv <= rv_eff
    if op == "eq":
        return abs(lv - rv_eff) < 1e-9
    return False


def eval_condition_at(cond: dict[str, Any], enriched: pd.DataFrame, i: int) -> bool:
    """在 bar 下标 i 上求单条条件；交叉需要 i>=1。"""
    if i < 0 or i >= len(enriched):
        return False
    return eval_condition(cond, enriched, i)


def _sequence_triggered(
    conditions: list[Any], enriched: pd.DataFrame, today_i: int, within_bars: int
) -> bool:
    """有序间隔：末步须在 today_i；相邻下标差 ∈ [0, within_bars]（存在性，非贪心）。"""
    if within_bars < 0 or not conditions:
        return False
    conds = [c for c in conditions if isinstance(c, dict)]
    if len(conds) != len(conditions):
        return False
    if not conds:
        return False
    if not eval_condition_at(conds[-1], enriched, today_i):
        return False

    def can_place(step: int, cursor: int) -> bool:
        """Place conditions[0..step] ending at cursor for step's condition; step goes backward."""
        if step < 0:
            return True
        lo = max(0, cursor - within_bars)
        for i in range(cursor, lo - 1, -1):
            if eval_condition_at(conds[step], enriched, i):
                if can_place(step - 1, i):
                    return True
        return False

    if len(conds) == 1:
        return True
    return can_place(len(conds) - 2, today_i)


def _within_triggered(
    conditions: list[Any], enriched: pd.DataFrame, today_i: int, within_bars: int
) -> bool:
    """近窗内每条至少一日为真；允许同日；无序。"""
    if within_bars < 0 or not conditions:
        return False
    lo = max(0, today_i - within_bars)
    for cond in conditions:
        if not isinstance(cond, dict):
            return False
        hit = False
        for i in range(lo, today_i + 1):
            if eval_condition_at(cond, enriched, i):
                hit = True
                break
        if not hit:
            return False
    return True


def _side_triggered(block: Any, enriched: pd.DataFrame, today_i: int) -> bool:
    if not isinstance(block, dict):
        return False
    conditions = block.get("conditions") or []
    if not conditions:
        return False
    combine = str(block.get("combine") or "all").strip().lower()
    if combine == "sequence":
        return _sequence_triggered(conditions, enriched, today_i, _parse_within_bars(block))
    if combine == "within":
        return _within_triggered(conditions, enriched, today_i, _parse_within_bars(block))
    results: list[bool] = []
    for cond in conditions:
        if isinstance(cond, dict):
            results.append(eval_condition(cond, enriched, today_i))
        else:
            results.append(False)
    if not results:
        return False
    if combine == "any":
        return any(results)
    return all(results)


def eval_factor_rules(data: dict[str, Any], ctx: Any) -> list[Signal]:
    """
    求值 factor_rules 策略。

    同 bar 买卖皆满足时卖优先。
    """
    row = ctx.get("row") if isinstance(ctx, dict) else getattr(ctx, "row", {}) or {}
    history = ctx.get("history") if isinstance(ctx, dict) else None
    symbol = str(row.get("symbol") or data.get("symbol") or "UNKNOWN")

    if history is None or getattr(history, "empty", True) or len(history) < 2:
        return []

    names = collect_factor_names(data)
    db = ctx.get("db") if isinstance(ctx, dict) else None
    enriched = enrich_history_with_factors(history, names, db=db)
    if enriched is None or len(enriched) < 2:
        return []

    today_i = len(enriched) - 1
    sell_on = _side_triggered(data.get("sell"), enriched, today_i)
    buy_on = _side_triggered(data.get("buy"), enriched, today_i)

    if sell_on:
        return [Signal(symbol=symbol, side=Side.SELL, reason="factor_rules_sell")]
    if buy_on:
        return [Signal(symbol=symbol, side=Side.BUY, reason="factor_rules_buy")]
    return []
