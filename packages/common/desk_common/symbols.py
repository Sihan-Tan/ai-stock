"""标的代码规范化。"""

from __future__ import annotations


def normalize_symbol(raw: str) -> str:
    """
    将多种写法归一为 `600519.SH` / `000001.SZ` 形式。

    @param raw: 原始代码，如 `sh600519`、`600519`、`600519.SH`
    @returns: 规范化符号
    """
    s = raw.strip().upper().replace(" ", "")
    if "." in s:
        code, mkt = s.split(".", 1)
        mkt = "SH" if mkt in {"SH", "SS", "XSHG"} else "SZ" if mkt in {"SZ", "XSHE"} else mkt
        return f"{code.zfill(6)}.{mkt}"
    if s.startswith("SH") or s.startswith("SZ"):
        return f"{s[2:].zfill(6)}.{s[:2]}"
    code = "".join(ch for ch in s if ch.isdigit()).zfill(6)
    if code.startswith(("5", "6", "9")):
        return f"{code}.SH"
    return f"{code}.SZ"
