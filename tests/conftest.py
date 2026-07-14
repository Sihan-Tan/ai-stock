"""把各包加入 sys.path（无需复杂 editable 也可测）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = [
    ROOT / "apps" / "api",
    ROOT / "packages" / "common",
    ROOT / "packages" / "db",
    ROOT / "packages" / "market",
    ROOT / "packages" / "sentiment",
    ROOT / "packages" / "lhb",
    ROOT / "packages" / "calendar",
    ROOT / "packages" / "knowledge",
    ROOT / "packages" / "factor",
    ROOT / "packages" / "ml",
    ROOT / "packages" / "indicators",
    ROOT / "packages" / "strategy",
    ROOT / "packages" / "backtest",
    ROOT / "packages" / "broker",
    ROOT / "packages" / "alert",
    ROOT / "packages" / "ai",
    ROOT / "packages" / "review",
    ROOT / "packages" / "morning_brief",
]
for p in paths:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
