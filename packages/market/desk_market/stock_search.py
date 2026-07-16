"""全市场标的搜索：代码 / 名称 / 拼音。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import SecurityMeta

try:
    from pypinyin import Style, lazy_pinyin
except Exception:  # pragma: no cover
    Style = None  # type: ignore
    lazy_pinyin = None  # type: ignore


def name_pinyin_keys(name: str) -> tuple[str, str]:
    """
    生成名称的全拼与首字母串（小写、无空格）。

    @param name: 中文名称
    @returns: (full_pinyin, initials)
    """
    text = (name or "").strip()
    if not text:
        return "", ""
    if lazy_pinyin is None or Style is None:
        return "", ""
    full = "".join(lazy_pinyin(text)).lower()
    initials = "".join(lazy_pinyin(text, style=Style.FIRST_LETTER)).lower()
    return full, initials


def _query_code_forms(q: str) -> set[str]:
    """
    从查询串推导可能的代码形态，便于与 symbol 比较。

    @param q: 原始查询（已 strip）
    """
    forms: set[str] = {q.upper(), q.lower(), q}
    compact = q.replace(" ", "")
    forms.add(compact.upper())
    try:
        forms.add(normalize_symbol(compact).upper())
    except Exception:  # noqa: BLE001
        pass
    if compact.isdigit() and len(compact) <= 6:
        forms.add(compact)
    return {f for f in forms if f}


def _score_hit(
    *,
    symbol: str,
    name: str,
    q: str,
    q_lower: str,
    code_forms: set[str],
) -> tuple[int, str] | None:
    """
    计算命中优先级；未命中返回 None。

    分数越小越优先：0 代码精确，1 名称前缀，2 拼音首字母前缀，3 其它包含。

    @returns: (score, match_type) 或 None
    """
    sym_u = symbol.upper()
    name_s = name or ""
    name_lower = name_s.lower()

    for form in code_forms:
        fu = form.upper()
        if fu == sym_u or fu == sym_u.split(".")[0]:
            return 0, "code"
    for form in code_forms:
        fu = form.upper()
        if sym_u.startswith(fu) or sym_u.split(".")[0].startswith(fu):
            return 3, "code"
        if fu and fu in sym_u:
            return 3, "code"

    if q and name_s.startswith(q):
        return 1, "name"
    if q_lower and name_lower.startswith(q_lower):
        return 1, "name"
    if q and q in name_s:
        return 3, "name"
    if q_lower and q_lower in name_lower:
        return 3, "name"

    full, initials = name_pinyin_keys(name_s)
    if q_lower and initials.startswith(q_lower):
        return 2, "pinyin"
    if q_lower and full.startswith(q_lower):
        return 2, "pinyin"
    if q_lower and (q_lower in initials or q_lower in full):
        return 3, "pinyin"

    return None


def search_securities(db: Session, q: str, *, limit: int = 6) -> list[dict[str, Any]]:
    """
    在市标的中按代码/名称/拼音搜索，返回排序后的前 limit 条。

    @param db: Session
    @param q: 查询串
    @param limit: 最大条数（调用方已钳制）
    """
    query = (q or "").strip()
    if not query:
        return []

    limit = max(1, min(int(limit), 50))
    q_lower = query.lower().replace(" ", "")
    code_forms = _query_code_forms(query)

    rows = db.scalars(
        select(SecurityMeta).where(SecurityMeta.is_delisted.is_(False))
    ).all()

    scored: list[tuple[int, str, dict[str, Any]]] = []
    for row in rows:
        hit = _score_hit(
            symbol=row.symbol,
            name=row.name,
            q=query,
            q_lower=q_lower,
            code_forms=code_forms,
        )
        if hit is None:
            continue
        score, match_type = hit
        scored.append(
            (
                score,
                row.symbol,
                {
                    "symbol": row.symbol,
                    "name": row.name,
                    "match_type": match_type,
                },
            )
        )

    scored.sort(key=lambda x: (x[0], x[1]))
    return [item for _, _, item in scored[:limit]]
