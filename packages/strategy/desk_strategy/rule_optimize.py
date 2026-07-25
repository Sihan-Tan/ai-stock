"""因子规则预填、阈值网格与选优。"""

from __future__ import annotations

import copy
import itertools
import re
from typing import Any

import yaml

OSCILLATOR_TOKENS = ("RSI", "CCI", "WILLR", "WR", "STOCH", "KDJ", "MOM")
MAX_GRID = 200

DEFAULT_BUY_GRID = [0.5, 0.55, 0.6, 0.65, 0.7]
DEFAULT_SELL_GRID = [0.3, 0.35, 0.4, 0.45, 0.5]
DEFAULT_POSITION_PCTS = [50, 100]
DEFAULT_MAX_HOLD_BARS_LIST = [0, 5, 10, 20]

_COMPARE_OPS = frozenset({"gt", "gte", "lt", "lte", "eq"})


def _safe_id_part(name: str) -> str:
    """因子名 → 可作策略 id 片段的安全字符串。"""
    s = re.sub(r"[^A-Za-z0-9]+", "_", name.strip())
    return s.strip("_") or "factor"


def _is_oscillator(name: str) -> bool:
    """因子名（忽略大小写）是否含振荡类 token。"""
    upper = name.upper()
    return any(tok in upper for tok in OSCILLATOR_TOKENS)


def _is_ma_like(name: str) -> bool:
    """名称大写是否以 SMA / EMA / MA 开头。"""
    upper = name.upper()
    return upper.startswith("SMA") or upper.startswith("EMA") or upper.startswith("MA")


def _cond_compare(factor: str, op: str, const: float) -> dict[str, Any]:
    """构造因子 vs 常数比较条件。"""
    return {"op": op, "left": {"factor": factor}, "right": {"const": const}}


def _cond_cross(left: str, op: str, right: str) -> dict[str, Any]:
    """构造交叉条件。"""
    return {"op": op, "left": {"factor": left}, "right": {"factor": right}}


def build_prefill_doc(factor_names: list[str]) -> dict[str, Any]:
    """
    由勾选因子生成 factor_rules 草稿文档。

    ml:* → buy gt 0.6 / sell lt 0.4；
    振荡类 → buy lt 30 / sell gt 70；
    均线类 → CLOSE cross_* factor；
    其它 TA → factor cross_* SMA_20。
    """
    names = [n.strip() for n in factor_names if isinstance(n, str) and n.strip()]
    first = names[0] if names else "factor"
    sid = f"rule_from_{_safe_id_part(first)}"

    buy_conds: list[dict[str, Any]] = []
    sell_conds: list[dict[str, Any]] = []

    for name in names:
        if name.lower().startswith("ml:"):
            buy_conds.append(_cond_compare(name, "gt", 0.6))
            sell_conds.append(_cond_compare(name, "lt", 0.4))
        elif _is_oscillator(name):
            buy_conds.append(_cond_compare(name, "lt", 30))
            sell_conds.append(_cond_compare(name, "gt", 70))
        elif _is_ma_like(name):
            buy_conds.append(_cond_cross("CLOSE", "cross_up", name))
            sell_conds.append(_cond_cross("CLOSE", "cross_down", name))
        else:
            buy_conds.append(_cond_cross(name, "cross_up", "SMA_20"))
            sell_conds.append(_cond_cross(name, "cross_down", "SMA_20"))

    return {
        "id": sid,
        "name": sid,
        "kind": "factor_rules",
        "version": "v0.1",
        "params": {"position_pct": 100, "max_hold_bars": 0},
        "buy": {"combine": "all", "conditions": buy_conds},
        "sell": {"combine": "any", "conditions": sell_conds},
    }


def _is_const_compare(cond: Any) -> bool:
    """是否为因子 vs 常数的比较算子条件。"""
    if not isinstance(cond, dict):
        return False
    op = str(cond.get("op") or "").strip().lower()
    if op not in _COMPARE_OPS:
        return False
    left = cond.get("left")
    right = cond.get("right")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    has_factor = isinstance(left.get("factor"), str) and bool(str(left.get("factor")).strip())
    has_const = "const" in right
    # 也允许 left=const / right=factor
    if has_factor and has_const:
        return True
    has_factor_r = isinstance(right.get("factor"), str) and bool(str(right.get("factor")).strip())
    has_const_l = "const" in left
    return bool(has_factor_r and has_const_l)


def list_const_compare_slots(doc: dict[str, Any], side: str) -> list[dict[str, Any]]:
    """列出某侧可优化的因子-常数比较条件（返回条件引用列表，浅引用）。"""
    block = doc.get(side) if isinstance(doc, dict) else None
    if not isinstance(block, dict):
        return []
    out: list[dict[str, Any]] = []
    for cond in block.get("conditions") or []:
        if _is_const_compare(cond):
            out.append(cond)
    return out


def has_optimizable_const_compares(doc: dict[str, Any]) -> bool:
    """文档买卖侧是否存在可优化的因子 vs 常数比较。"""
    return bool(
        list_const_compare_slots(doc, "buy") or list_const_compare_slots(doc, "sell")
    )


def _set_compare_const(cond: dict[str, Any], value: float) -> None:
    """将比较条件中的 const 侧设为 value。"""
    left = cond.get("left")
    right = cond.get("right")
    if isinstance(right, dict) and "const" in right:
        right["const"] = value
    elif isinstance(left, dict) and "const" in left:
        left["const"] = value


def apply_threshold_params(
    doc: dict[str, Any],
    *,
    buy_v: float | None,
    sell_v: float | None,
    position_pct: float,
    max_hold_bars: int,
) -> dict[str, Any]:
    """
    深拷贝文档；买侧所有因子-常数比较同步为 buy_v（非空时）；卖侧同理；
    并写入 params.position_pct / max_hold_bars。
    """
    out = copy.deepcopy(doc)
    if buy_v is not None:
        for cond in list_const_compare_slots(out, "buy"):
            _set_compare_const(cond, float(buy_v))
    if sell_v is not None:
        for cond in list_const_compare_slots(out, "sell"):
            _set_compare_const(cond, float(sell_v))
    params = out.get("params")
    if not isinstance(params, dict):
        params = {}
        out["params"] = params
    else:
        params = dict(params)
        out["params"] = params
    params["position_pct"] = float(position_pct)
    params["max_hold_bars"] = int(max_hold_bars)
    return out


def _grid_len(xs: list[Any] | None) -> int:
    """空/None 网格计为 1（单次透传）。"""
    if xs is None or len(xs) == 0:
        return 1
    return len(xs)


def count_grid(
    buy_grid: list[Any] | None,
    sell_grid: list[Any] | None,
    position_pcts: list[Any] | None,
    max_hold_bars_list: list[Any] | None,
) -> int:
    """计算网格组合数；缺失侧按 1 计。"""
    return (
        _grid_len(buy_grid)
        * _grid_len(sell_grid)
        * _grid_len(position_pcts)
        * _grid_len(max_hold_bars_list)
    )


def validate_grid(
    buy_grid: list[Any] | None,
    sell_grid: list[Any] | None,
    position_pcts: list[Any] | None,
    max_hold_bars_list: list[Any] | None,
) -> None:
    """组合数超过 MAX_GRID 时抛 ValueError。"""
    n = count_grid(buy_grid, sell_grid, position_pcts, max_hold_bars_list)
    if n > MAX_GRID:
        raise ValueError(f"grid too large: {n} > {MAX_GRID}")


def pick_best_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    选优：最大化 total_return；平局取 max_drawdown 更大者（如 -0.1 优于 -0.2）。
    """
    if not results:
        raise ValueError("empty results")

    def key_fn(item: dict[str, Any]) -> tuple[float, float]:
        m = item.get("metrics") or {}
        tr = float(m.get("total_return") or 0.0)
        dd = float(m.get("max_drawdown") or 0.0)
        return (tr, dd)

    return max(results, key=key_fn)


def optimize_rules_yaml(
    db: Any,
    *,
    symbol: str,
    start: Any,
    end: Any,
    yaml_body: dict[str, Any] | str,
    buy_grid: list[float] | None = None,
    sell_grid: list[float] | None = None,
    position_pcts: list[float] | None = None,
    max_hold_bars_list: list[int] | None = None,
    initial_cash: float = 1_000_000.0,
) -> dict[str, Any]:
    """
    对 factor_rules 文档网格寻优买卖阈值 / 仓位% / 最长持仓。

    @returns: {best, tried, skipped}
    """
    if isinstance(yaml_body, str):
        parsed = yaml.safe_load(yaml_body)
    else:
        parsed = yaml_body
    if not isinstance(parsed, dict):
        raise ValueError("yaml_body must be a mapping")
    if not has_optimizable_const_compares(parsed):
        raise ValueError("无可优化阈值条件")

    buy_slots = list_const_compare_slots(parsed, "buy")
    sell_slots = list_const_compare_slots(parsed, "sell")

    bg = list(buy_grid) if buy_grid is not None else list(DEFAULT_BUY_GRID)
    sg = list(sell_grid) if sell_grid is not None else list(DEFAULT_SELL_GRID)
    pps = list(position_pcts) if position_pcts is not None else list(DEFAULT_POSITION_PCTS)
    holds = (
        list(max_hold_bars_list)
        if max_hold_bars_list is not None
        else list(DEFAULT_MAX_HOLD_BARS_LIST)
    )

    buy_vals: list[float | None] = [None] if not buy_slots else bg  # type: ignore[assignment]
    sell_vals: list[float | None] = [None] if not sell_slots else sg  # type: ignore[assignment]

    validate_grid(buy_vals, sell_vals, pps, holds)

    from desk_backtest import BacktraderRunner
    from desk_common.contracts import BacktestRequest

    runner = BacktraderRunner(db)
    strategy_id = str(parsed.get("id") or "opt_rules")
    results: list[dict[str, Any]] = []
    skipped = 0

    for buy_v, sell_v, pos, hold in itertools.product(buy_vals, sell_vals, pps, holds):
        doc = apply_threshold_params(
            parsed,
            buy_v=buy_v,
            sell_v=sell_v,
            position_pct=float(pos),
            max_hold_bars=int(hold),
        )
        text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
        try:
            report = runner.run(
                BacktestRequest(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    start=start,
                    end=end,
                    initial_cash=initial_cash,
                    bar_period="1d",
                ),
                persist=False,
                yaml_override=text,
            )
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        metrics = {
            "total_return": float(report.total_return),
            "max_drawdown": float(report.max_drawdown),
            "trades": int(report.trades),
            "sharpe": report.sharpe,
        }
        results.append(
            {
                "yaml_body": doc,
                "metrics": metrics,
                "buy_threshold": buy_v,
                "sell_threshold": sell_v,
                "position_pct": float(pos),
                "max_hold_bars": int(hold),
            }
        )

    if not results:
        raise ValueError("寻优无有效结果")

    best = pick_best_result(results)
    return {
        "best": {
            "yaml_body": best["yaml_body"],
            "metrics": best["metrics"],
            "buy_threshold": best.get("buy_threshold"),
            "sell_threshold": best.get("sell_threshold"),
            "position_pct": best.get("position_pct"),
            "max_hold_bars": best.get("max_hold_bars"),
        },
        "tried": len(results),
        "skipped": skipped,
    }
