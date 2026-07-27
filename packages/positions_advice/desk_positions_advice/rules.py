"""hybrid 模式：简单规则候选动作。"""

from __future__ import annotations

from typing import Any


def rule_candidates(
    positions: list[dict[str, Any]],
    *,
    session_kind: str,
) -> list[dict[str, Any]]:
    """
    为每只持仓给出规则候选（不强制最终动作）。

    尾盘：日跌幅 <= -5% 或浮亏相对成本 <= -8% → 卖出，否则持有。
    早盘：日涨 >= 5% → 高抛低吸；日跌 <= -3% → 低吸；浮亏严重 → 卖出；否则持有。
    """
    out: list[dict[str, Any]] = []
    for p in positions:
        try:
            sym = str(p.get("symbol") or "")
            if not sym:
                continue
            cost = float(p.get("cost") or 0) or 0.0
            last = float(p.get("last_price") or cost) or 0.0
            day = p.get("day_chg_pct")
            day_pct = float(day) if day is not None else None
            pnl_pct = ((last / cost) - 1.0) if cost > 0 else 0.0

            if session_kind == "morning":
                if pnl_pct <= -0.08 or (day_pct is not None and day_pct <= -0.05):
                    action, why = "卖出", "浮亏或竞价/日内跌幅偏大"
                elif day_pct is not None and day_pct >= 0.05:
                    action, why = "高抛低吸", "冲高可考虑高抛低吸"
                elif day_pct is not None and day_pct <= -0.03:
                    action, why = "低吸", "回调可考虑低吸"
                else:
                    action, why = "持有", "未见明确强弱信号"
            else:
                if (day_pct is not None and day_pct <= -0.05) or pnl_pct <= -0.08:
                    action, why = "卖出", "尾盘跌幅或浮亏偏大，不宜隔夜"
                else:
                    action, why = "持有", "跌幅可控，规则建议持有"

            out.append(
                {
                    "symbol": sym,
                    "action": action,
                    "rule_reason": why,
                }
            )
        except Exception:  # noqa: BLE001
            continue
    return out
