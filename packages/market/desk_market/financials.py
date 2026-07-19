"""财务服务：缓存、QMT→akshare 降级、同行对比与估值。"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta
from typing import Any, Callable, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from desk_common.symbols import normalize_symbol
from desk_db.models import BarDaily, FinancialSnapshot, QuoteSnapshot
from desk_market.akshare_financials import fetch_akshare_financials
from desk_market.qmt_financials import MockQmtFinancials, XtdataFinancials, _STANDARD_KEYS

if TYPE_CHECKING:
    from desk_market import MarketService

_DEFAULT_TABLES: list[str] = [
    "Abstract",
    "Income",
    "Pershareindex",
    "Balance",
    "CashFlow",
]

_CACHE_TABLES: frozenset[str] = frozenset(
    {"Abstract", "Income", "Pershareindex", "Balance", "CashFlow", "Capital"}
)


def _default_qmt() -> Any:
    """优先真实 QMT；不可用时用失败 Mock，以便降级 akshare。"""
    try:
        return XtdataFinancials()
    except Exception:  # noqa: BLE001
        return MockQmtFinancials(fail=True)


def _merge_row(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """合并两行：非空字段覆盖。"""
    out = dict(base)
    for key, value in extra.items():
        if value is None or value == "":
            continue
        out[key] = value
    return out


def _metrics_from_tables(tables: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """
    将多表行按 period 合并为 metrics 序列（新→旧）。

    @param tables: ``table_name → [row...]``
    """
    by_period: dict[str, dict[str, Any]] = {}
    # Abstract 优先作为基底，其余表补充
    order = ["Abstract", "Pershareindex", "Income", "Balance", "CashFlow", "Capital"]
    for table in order:
        rows = tables.get(table) or []
        for row in rows:
            period = row.get("period")
            if not period:
                continue
            key = str(period)
            existing = by_period.get(key, {"period": key})
            by_period[key] = _merge_row(existing, row)
    metrics = list(by_period.values())
    metrics.sort(key=lambda r: str(r.get("period") or ""), reverse=True)
    return metrics


def _safe_div(numer: float | None, denom: float | None) -> float | None:
    """安全除法；分母无效时返回 None。"""
    if numer is None or denom is None:
        return None
    try:
        d = float(denom)
        if d == 0:
            return None
        return float(numer) / d
    except (TypeError, ValueError):
        return None


def _percentile_rank(values: list[float], current: float) -> float:
    """
    当前值在序列中的分位（0–100）。

    @param values: 历史样本（含当前）
    @param current: 当前值
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    below = sum(1 for v in sorted_vals if v < current)
    equal = sum(1 for v in sorted_vals if v == current)
    return 100.0 * (below + 0.5 * equal) / len(sorted_vals)


class FinancialService:
    """财务取数与估值：缓存 → QMT → akshare。"""

    def __init__(
        self,
        db: Session,
        qmt: Any | None = None,
        akshare_fetch: Callable[..., dict[str, Any]] | None = None,
        ttl_days: int = 7,
        market: MarketService | None = None,
    ) -> None:
        """
        @param db: SQLAlchemy Session
        @param qmt: QMT 财务源；默认尝试 Xtdata，失败则 Mock(fail=True)
        @param akshare_fetch: akshare 拉取函数；默认 ``fetch_akshare_financials``
        @param ttl_days: 缓存有效天数
        @param market: 可选行情服务（估值取现价）
        """
        self.db = db
        self.qmt = qmt if qmt is not None else _default_qmt()
        self.akshare_fetch = akshare_fetch or fetch_akshare_financials
        self.ttl_days = max(int(ttl_days), 0)
        self.market = market

    def get_financials(self, symbol: str, years: int = 5) -> dict[str, Any]:
        """
        缓存 → qmt → akshare；返回 ``{symbol, source, metrics, tables?, error?}``。

        @param symbol: 原始或可规范化代码
        @param years: 最近若干自然年
        """
        sym = normalize_symbol(symbol)
        cached = self._read_cache(sym, years=years)
        if cached is not None:
            return cached

        errors: list[str] = []
        fetched: dict[str, Any] | None = None

        try:
            fetched = self.qmt.get_financials(sym, tables=list(_DEFAULT_TABLES), years=years)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"qmt: {exc}")

        if fetched is None or not (fetched.get("tables") or {}):
            try:
                fetched = self.akshare_fetch(sym, years=years)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"akshare: {exc}")
                fetched = None

        if fetched is None:
            return {
                "symbol": sym,
                "source": None,
                "metrics": [],
                "error": "; ".join(errors) or "financials unavailable",
            }

        tables = fetched.get("tables") or {}
        source = str(fetched.get("source") or "unknown")
        self._upsert_snapshots(sym, tables, source=source)
        metrics = _metrics_from_tables(tables)
        return {
            "symbol": sym,
            "source": source,
            "metrics": metrics,
            "tables": tables,
        }

    def peer_compare(self, symbols: list[str], years: int = 5) -> dict[str, Any]:
        """
        批量 ``get_financials``，拼 latest 指标表 + ``missing[]``。

        @param symbols: 对比标的列表
        @param years: 财务窗口
        """
        rows: list[dict[str, Any]] = []
        missing: list[str] = []
        for raw in symbols:
            sym = normalize_symbol(raw)
            out = self.get_financials(sym, years=years)
            if out.get("error") or not out.get("metrics"):
                missing.append(sym)
                continue
            latest = dict(out["metrics"][0])
            latest["symbol"] = sym
            latest["source"] = out.get("source")
            rows.append(latest)
        return {"rows": rows, "missing": missing}

    def get_valuation(
        self, symbol: str, peers: list[str] | None = None
    ) -> dict[str, Any]:
        """
        现价 / PE / PB / 历史分位；可选相对 peers 中位数。

        @param symbol: 标的
        @param peers: 可选同行列表
        """
        sym = normalize_symbol(symbol)
        price = self._latest_price(sym)
        fin = self.get_financials(sym)
        metrics = list(fin.get("metrics") or [])
        latest = metrics[0] if metrics else {}
        eps = latest.get("eps")
        bps = latest.get("bps")
        pe = _safe_div(price, float(eps) if eps is not None else None)
        pb = _safe_div(price, float(bps) if bps is not None else None)
        revenue = latest.get("revenue")
        total_shares = latest.get("total_shares")
        ps = None
        if price is not None and revenue is not None and total_shares:
            sales_per_share = _safe_div(float(revenue), float(total_shares))
            ps = _safe_div(price, sales_per_share)

        pe_series: list[float] = []
        if price is not None:
            for row in metrics:
                row_eps = row.get("eps")
                row_pe = _safe_div(price, float(row_eps) if row_eps is not None else None)
                if row_pe is not None:
                    pe_series.append(row_pe)

        notes: list[str] = []
        pe_percentile: float | None = None
        if len(pe_series) < 3:
            notes.append("pe history sample < 3; percentile unavailable")
        elif pe is not None:
            pe_percentile = _percentile_rank(pe_series, pe)

        result: dict[str, Any] = {
            "symbol": sym,
            "price": price,
            "pe": pe,
            "pb": pb,
            "ps": ps,
            "pe_percentile": pe_percentile,
            "source": fin.get("source"),
            "eps": eps,
            "bps": bps,
        }
        if notes:
            result["note"] = "; ".join(notes)

        if peers:
            peer_pes: list[float] = []
            for peer in peers:
                peer_out = self.get_valuation(peer, peers=None)
                if peer_out.get("pe") is not None:
                    peer_pes.append(float(peer_out["pe"]))
            if peer_pes and pe is not None:
                median_pe = statistics.median(peer_pes)
                result["peer_pe_median"] = median_pe
                result["pe_vs_peers"] = _safe_div(pe, median_pe)
            else:
                result["peer_pe_median"] = None
                result["pe_vs_peers"] = None
                result["note"] = (
                    (result.get("note") + "; ") if result.get("note") else ""
                ) + "peer pe unavailable"

        if fin.get("error"):
            result["error"] = fin["error"]
        return result

    def _read_cache(self, symbol: str, years: int = 5) -> dict[str, Any] | None:
        """
        读取 TTL 内缓存；Abstract 或关键表齐全时组装 metrics。

        @param symbol: 已规范化 symbol
        @param years: 报告期窗口（按 period 字符串过滤）
        """
        cutoff = datetime.utcnow() - timedelta(days=self.ttl_days)
        rows = self.db.scalars(
            select(FinancialSnapshot).where(
                FinancialSnapshot.symbol == symbol,
                FinancialSnapshot.fetched_at >= cutoff,
            )
        ).all()
        if not rows:
            return None

        tables: dict[str, list[dict[str, Any]]] = {}
        sources: list[str] = []
        start_year = datetime.utcnow().year - max(years, 1) + 1
        period_cutoff = f"{start_year}0101"
        for row in rows:
            if row.table_name not in _CACHE_TABLES:
                continue
            try:
                payload = json.loads(row.payload_json or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            period = str(payload.get("period") or row.period or "")
            if period and period < period_cutoff:
                continue
            item = dict(payload)
            if period and not item.get("period"):
                item["period"] = period
            tables.setdefault(row.table_name, []).append(item)
            if row.source:
                sources.append(row.source)

        if not tables.get("Abstract") and not tables.get("Pershareindex") and not tables.get(
            "Income"
        ):
            return None

        metrics = _metrics_from_tables(tables)
        if not metrics:
            return None
        source = sources[0] if sources else "cache"
        return {
            "symbol": symbol,
            "source": source,
            "metrics": metrics,
            "tables": tables,
        }

    def _upsert_snapshots(
        self,
        symbol: str,
        tables: dict[str, list[dict[str, Any]]],
        *,
        source: str,
    ) -> None:
        """
        按 period/table 写入或更新 FinancialSnapshot。

        @param symbol: 标的
        @param tables: 拉取到的表
        @param source: qmt|akshare
        """
        now = datetime.utcnow()
        for table_name, rows in tables.items():
            if table_name not in _CACHE_TABLES:
                continue
            for row in rows or []:
                period = str(row.get("period") or "")
                if not period:
                    continue
                payload = {k: row.get(k) for k in _STANDARD_KEYS if k in row or k == "period"}
                payload["period"] = period
                # 保留标准 key 之外的有用字段（如已存在）
                for key, value in row.items():
                    if key not in payload:
                        payload[key] = value
                existing = self.db.scalar(
                    select(FinancialSnapshot).where(
                        FinancialSnapshot.symbol == symbol,
                        FinancialSnapshot.table_name == table_name,
                        FinancialSnapshot.period == period,
                    )
                )
                payload_json = json.dumps(payload, ensure_ascii=False)
                if existing:
                    existing.source = source
                    existing.payload_json = payload_json
                    existing.fetched_at = now
                else:
                    self.db.add(
                        FinancialSnapshot(
                            symbol=symbol,
                            table_name=table_name,
                            period=period,
                            source=source,
                            payload_json=payload_json,
                            fetched_at=now,
                        )
                    )
        self.db.flush()

    def _latest_price(self, symbol: str) -> float | None:
        """
        取现价：QuoteSnapshot.last，否则最近日线 close。

        @param symbol: 已规范化 symbol
        """
        session = self.market.db if self.market is not None else self.db
        quote = session.scalar(
            select(QuoteSnapshot).where(QuoteSnapshot.symbol == symbol)
        )
        if quote is not None and quote.last is not None:
            try:
                last = float(quote.last)
                if last > 0:
                    return last
            except (TypeError, ValueError):
                pass
        bar = session.scalar(
            select(BarDaily)
            .where(BarDaily.symbol == symbol)
            .order_by(BarDaily.ts.desc())
            .limit(1)
        )
        if bar is not None and bar.close is not None:
            try:
                close = float(bar.close)
                if close > 0:
                    return close
            except (TypeError, ValueError):
                pass
        return None
