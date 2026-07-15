"""价格精度工具。"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import SupportsFloat


def round_price(value: SupportsFloat) -> float:
    """
    价格入库精度：保留小数点后 3 位（四舍五入）。

    @param value: 原始价格
    @returns: 三位小数 float
    """
    quantized = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return float(quantized)
