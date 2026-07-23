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
ALL_OPS = COMPARE_OPS | CROSS_OPS
_ML_PREFIX = "ml:"


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
    """因子主输出列名；ml: 列名即因子名。"""
    if factor_name.startswith(_ML_PREFIX):
        return factor_name
    meta = get_factor(factor_name)
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
    ta_names = [n for n in factor_names if not str(n).startswith(_ML_PREFIX)]
    specs: list[dict[str, Any]] = []
    for raw in ta_names:
        meta = get_factor(raw)
        if meta is None:
            continue
        specs.append(
            {
                "talib": meta["talib"],
                "params": dict(meta.get("params") or {}),
                "outputs": list(meta.get("outputs") or []),
            }
        )
    if not specs:
        return out
    # 保证列名小写 OHLCV
    rename = {}
    for col in list(out.columns):
        low = str(col).lower()
        if low in {"open", "high", "low", "close", "volume"} and col != low:
            rename[col] = low
    if rename:
        out = out.rename(columns=rename)
    return apply_factor_specs(out, specs)


def _resolve_operand(
    operand: Any,
    cur: pd.Series,
    prev: pd.Series,
    *,
    use_prev: bool = False,
) -> float | None:
    """解析操作数：常数或因子列。"""
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
    row = prev if use_prev else cur
    if col not in row.index:
        # 尝试小写
        col_l = col.lower()
        if col_l in row.index:
            col = col_l
        else:
            return None
    return _as_float(row.get(col))


def eval_condition(cond: dict[str, Any], cur: pd.Series, prev: pd.Series) -> bool:
    """
    单条件求值。

    未知因子 / 缺值 → False。
    """
    op = str(cond.get("op") or "").strip().lower()
    if op not in ALL_OPS:
        return False
    left = cond.get("left")
    right = cond.get("right")
    if op in CROSS_OPS:
        l0 = _resolve_operand(left, cur, prev, use_prev=False)
        r0 = _resolve_operand(right, cur, prev, use_prev=False)
        l1 = _resolve_operand(left, cur, prev, use_prev=True)
        r1 = _resolve_operand(right, cur, prev, use_prev=True)
        if None in (l0, r0, l1, r1):
            return False
        if op == "cross_up":
            return l1 <= r1 and l0 > r0
        return l1 >= r1 and l0 < r0

    lv = _resolve_operand(left, cur, prev)
    rv = _resolve_operand(right, cur, prev)
    if lv is None or rv is None:
        return False
    if op == "gt":
        return lv > rv
    if op == "gte":
        return lv >= rv
    if op == "lt":
        return lv < rv
    if op == "lte":
        return lv <= rv
    if op == "eq":
        return abs(lv - rv) < 1e-9
    return False


def _side_triggered(block: Any, cur: pd.Series, prev: pd.Series) -> bool:
    """买卖侧是否触发。"""
    if not isinstance(block, dict):
        return False
    conditions = block.get("conditions") or []
    if not conditions:
        return False
    combine = str(block.get("combine") or "all").strip().lower()
    results: list[bool] = []
    for cond in conditions:
        if isinstance(cond, dict):
            results.append(eval_condition(cond, cur, prev))
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

    cur = enriched.iloc[-1]
    prev = enriched.iloc[-2]
    sell_on = _side_triggered(data.get("sell"), cur, prev)
    buy_on = _side_triggered(data.get("buy"), cur, prev)

    if sell_on:
        return [Signal(symbol=symbol, side=Side.SELL, reason="factor_rules_sell")]
    if buy_on:
        return [Signal(symbol=symbol, side=Side.BUY, reason="factor_rules_buy")]
    return []
