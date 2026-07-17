"""东方财富个股所属行业 / 概念适配。"""

from __future__ import annotations

import logging
from typing import Any

import requests

from desk_common.symbols import normalize_symbol

logger = logging.getLogger(__name__)

_CORE_CONCEPTION_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax"
)
_STOCK_GET_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://emweb.securities.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}


class EmBoardsClient:
    """
    东方财富个股板块客户端。

    测试可注入实现同一 ``fetch`` 接口的 Fake。
    """

    def __init__(self, *, timeout: float = 12.0) -> None:
        """
        @param timeout: HTTP 超时秒数
        """
        self._timeout = timeout
        self._session = requests.Session()
        # 忽略环境代理，避免本机坏代理导致详情页板块空白
        self._session.trust_env = False
        self._session.headers.update(_DEFAULT_HEADERS)

    def fetch(self, symbol: str) -> list[dict[str, str]]:
        """
        拉取个股当前所属行业与精选概念。

        行业快照接口失败时仍尝试 F10 所属板块，避免整页空白。

        @param symbol: 规范化或可规范化 symbol
        @returns: ``board_code/board_name/board_type`` 列表（sector|concept）
        @raises RuntimeError: 请求失败或无有效数据
        """
        sym = normalize_symbol(symbol)
        code, market = sym.split(".", maxsplit=1)
        if market not in {"SH", "SZ", "BJ"}:
            raise RuntimeError(f"East Money boards unsupported for {sym}")

        industry = self._fetch_industry(code, market)
        memberships = self._fetch_ssbk(code, market)
        boards = self._classify(industry=industry, memberships=memberships)
        if not boards:
            raise RuntimeError(f"East Money boards returned no data for {sym}")
        return boards

    def _fetch_industry(self, code: str, market: str) -> str | None:
        """
        从行情快照字段读取所属行业名称；失败返回 None，不阻断后续 F10。

        @param code: 纯数字代码
        @param market: SH|SZ|BJ
        """
        market_code = 1 if market == "SH" else 0
        try:
            response = self._session.get(
                _STOCK_GET_URL,
                params={
                    "fltt": "2",
                    "invt": "2",
                    "fields": "f57,f58,f127",
                    "secid": f"{market_code}.{code}",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = (response.json() or {}).get("data") or {}
        except Exception as exc:  # noqa: BLE001 — 行业源不可达时降级到 ssbk
            logger.warning("East Money industry fetch failed for %s.%s: %s", code, market, exc)
            return None
        name = data.get("f127")
        if name is None:
            return None
        text = str(name).strip()
        return text or None

    def _fetch_ssbk(self, code: str, market: str) -> list[dict[str, Any]]:
        """
        拉取 F10「所属板块」列表。

        @param code: 纯数字代码
        @param market: SH|SZ|BJ
        """
        em_code = f"{market}{code}"
        try:
            response = self._session.get(
                _CORE_CONCEPTION_URL,
                params={"code": em_code},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json() or {}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"East Money ssbk fetch failed: {exc}") from exc
        rows = payload.get("ssbk") or []
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _classify(
        self,
        *,
        industry: str | None,
        memberships: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """
        将行业字段与所属板块列表归类为 sector / concept，并标记最相关项。

        @param industry: 快照行业名（可为空）
        @param memberships: CoreConception ``ssbk`` 行
        """
        sectors: list[dict[str, Any]] = []
        concepts: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _add(
            board_code: str,
            board_name: str,
            board_type: str,
            *,
            rank: int | None = None,
        ) -> None:
            key = f"{board_type}:{board_code}"
            if not board_name or key in seen:
                return
            seen.add(key)
            item = {
                "board_code": board_code,
                "board_name": board_name,
                "board_type": board_type,
                "_rank": rank,
            }
            if board_type == "sector":
                sectors.append(item)
            else:
                concepts.append(item)

        industry_code: str | None = None
        for row in memberships:
            name = str(row.get("BOARD_NAME") or "").strip()
            code = str(row.get("BOARD_CODE") or "").strip()
            if industry and name == industry and code:
                industry_code = code
                break

        if industry:
            _add(industry_code or f"EM_IND_{industry}", industry, "sector", rank=2)

        for row in memberships:
            name = str(row.get("BOARD_NAME") or "").strip()
            code = str(row.get("BOARD_CODE") or "").strip() or name
            if not name:
                continue
            precise = row.get("IS_PRECISE")
            rank_raw = row.get("BOARD_RANK")
            try:
                rank = int(rank_raw) if rank_raw is not None else None
            except (TypeError, ValueError):
                rank = None

            # 精选概念
            if precise in (1, "1"):
                _add(code, name, "concept", rank=rank)
                continue

            # 行业链前几级（非精选）
            if rank is not None and rank <= 3:
                if industry and name == industry:
                    continue
                _add(code, name, "sector", rank=rank)

        return annotate_primary_boards(
            [_public_board(item) for item in [*sectors, *concepts]],
            industry=industry,
            ranks={
                f"{item['board_type']}:{item['board_code']}": item.get("_rank")
                for item in [*sectors, *concepts]
            },
        )


def _public_board(item: dict[str, Any]) -> dict[str, str]:
    """
    去掉内部排序字段，输出 API 板块结构。

    @param item: 含可选 ``_rank`` 的中间结构
    """
    return {
        "board_code": str(item["board_code"]),
        "board_name": str(item["board_name"]),
        "board_type": str(item["board_type"]),
    }


def annotate_primary_boards(
    boards: list[dict[str, Any]],
    *,
    industry: str | None = None,
    ranks: dict[str, int | None] | None = None,
) -> list[dict[str, Any]]:
    """
    为行业 / 概念各标记一项最相关（``is_primary``）。

    行业：优先匹配快照行业名；否则取行业链中 rank 最大（最细分）的一项；
    再否则取名称最短的一项。
    概念：优先名称与任一行业相同；否则取 rank 最小的精选概念；再否则取首项。

    @param boards: 板块列表
    @param industry: 可选行业快照名
    @param ranks: ``board_type:board_code`` → BOARD_RANK
    """
    ranks = ranks or {}
    sectors = [b for b in boards if b.get("board_type") == "sector"]
    concepts = [b for b in boards if b.get("board_type") == "concept"]

    primary_sector_code: str | None = None
    if industry:
        for board in sectors:
            if board.get("board_name") == industry:
                primary_sector_code = str(board["board_code"])
                break
    if primary_sector_code is None and sectors:
        ranked = []
        for board in sectors:
            key = f"sector:{board['board_code']}"
            rank = ranks.get(key)
            if rank is not None:
                ranked.append((int(rank), str(board["board_code"])))
        if ranked:
            primary_sector_code = max(ranked, key=lambda item: item[0])[1]
        else:
            primary_sector_code = min(
                sectors,
                key=lambda board: (len(str(board.get("board_name") or "")), str(board.get("board_name") or "")),
            )["board_code"]

    primary_concept_code: str | None = None
    sector_names = {str(board.get("board_name") or "") for board in sectors}
    if concepts:
        matched = [
            board
            for board in concepts
            if str(board.get("board_name") or "") in sector_names
            or (industry and str(board.get("board_name") or "") == industry)
        ]
        if matched:
            primary_concept_code = str(matched[0]["board_code"])
        else:
            ranked = []
            for board in concepts:
                key = f"concept:{board['board_code']}"
                rank = ranks.get(key)
                if rank is not None:
                    ranked.append((int(rank), str(board["board_code"])))
            if ranked:
                primary_concept_code = min(ranked, key=lambda item: item[0])[1]
            else:
                primary_concept_code = str(concepts[0]["board_code"])

    out: list[dict[str, Any]] = []
    for board in boards:
        item = dict(board)
        code = str(item.get("board_code") or "")
        btype = str(item.get("board_type") or "")
        item["is_primary"] = (
            (btype == "sector" and code == primary_sector_code)
            or (btype == "concept" and code == primary_concept_code)
        )
        out.append(item)

    # 最相关项排到各组前面，便于库内回读时也能高亮首项
    def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        btype = str(item.get("board_type") or "")
        type_order = 0 if btype == "sector" else 1 if btype == "concept" else 2
        primary_order = 0 if item.get("is_primary") else 1
        return (type_order, primary_order, str(item.get("board_name") or ""))

    out.sort(key=_sort_key)
    return out
