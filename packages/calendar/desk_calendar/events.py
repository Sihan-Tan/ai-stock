"""财经日历 / 重大新闻 / 催化剂：同步、查询与演示种子。"""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from desk_db.models import CalendarEvent

logger = logging.getLogger(__name__)

CATEGORIES = ("news", "macro", "earnings", "lockup", "ipo", "catalyst")


@dataclass
class EventDraft:
    """待写入的事件草稿。"""

    event_date: date
    title: str
    category: str = "macro"
    importance: int = 3
    summary: str = ""
    event_time: str = ""
    symbol: str = ""
    name: str = ""
    region: str = "CN"
    source: str = "seed"
    external_id: str = ""
    payload: dict[str, Any] | None = None


class CalendarEventsClient(Protocol):
    """外部财经事件数据源。"""

    def fetch(self, start: date, end: date) -> list[EventDraft]:
        """拉取 [start, end] 区间事件。"""
        ...


def _ext_id(source: str, *parts: object) -> str:
    """生成稳定 external_id。"""
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{digest}"


def _call_timeout(fn, timeout: float = 12.0, *args, **kwargs):
    """带超时调用，避免 akshare 挂死。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, *args, **kwargs)
        return fut.result(timeout=timeout)


class SeedCalendarEventsClient:
    """离线演示种子：当日重大 + 未来约 3 个月财经/催化剂。"""

    def fetch(self, start: date, end: date) -> list[EventDraft]:
        """生成区间内演示事件。"""
        drafts: list[EventDraft] = []
        today = date.today()
        # 当日重大新闻（始终附上，便于「今日」区有内容）
        for i, (title, summary, imp) in enumerate(
            (
                (
                    "央行公开市场操作与流动性预期",
                    "关注逆回购到期与资金面边际变化，可能影响高股息与券商情绪。",
                    5,
                ),
                (
                    "海外科技巨头指引与亚太风险偏好",
                    "美股科技指引若超预期，可能带动 A 股成长风格短线交易活跃。",
                    4,
                ),
                (
                    "产业政策与主题催化跟踪",
                    "留意新能源、半导体、军工等领域政策窗口与龙头公告。",
                    4,
                ),
            )
        ):
            d = today if start <= today <= end else start
            drafts.append(
                EventDraft(
                    event_date=d,
                    event_time="08:30" if i == 0 else ("09:15" if i == 1 else "10:00"),
                    category="news",
                    importance=imp,
                    title=title,
                    summary=summary,
                    region="CN" if i != 1 else "US",
                    source="seed",
                    external_id=_ext_id("seed", "news", d.isoformat(), i),
                )
            )

        # 未来宏观 / 财报 / 解禁 / IPO / 催化剂（按周节奏铺开）
        cursor = max(start, today)
        week = 0
        while cursor <= end:
            week += 1
            templates: list[tuple[str, str, int, str, str]] = [
                (
                    "macro",
                    f"中国制造业 PMI（预期）· W{week}",
                    5,
                    "09:00",
                    "关注扩张/收缩临界与政策预期差。",
                ),
                (
                    "macro",
                    f"美国非农/CPI 窗口跟踪 · W{week}",
                    4,
                    "20:30",
                    "影响美元与风险资产定价，映射到北向与成长股波动。",
                ),
                (
                    "earnings",
                    f"重点公司财报披露窗口 · W{week}",
                    4,
                    "17:00",
                    "跟踪业绩预告修正与机构预期差。",
                ),
                (
                    "lockup",
                    f"限售解禁高峰观察 · W{week}",
                    3,
                    "",
                    "关注解禁规模靠前标的的抛压与对冲需求。",
                ),
                (
                    "catalyst",
                    f"行业大会/订单催化窗口 · W{week}",
                    3,
                    "",
                    "主题催化：关注机器人、AI 算力、创新药等事件驱动。",
                ),
            ]
            if week % 3 == 0:
                templates.append(
                    (
                        "ipo",
                        f"新股申购/上市观察 · W{week}",
                        3,
                        "09:30",
                        "留意打新节奏与板块资金分流。",
                    )
                )
            for offset, (cat, title, imp, tm, summary) in enumerate(templates):
                day = cursor + timedelta(days=min(offset, 4))
                if day < start or day > end:
                    continue
                drafts.append(
                    EventDraft(
                        event_date=day,
                        event_time=tm,
                        category=cat,
                        importance=imp,
                        title=title,
                        summary=summary,
                        region="US" if "美国" in title else "CN",
                        source="seed",
                        external_id=_ext_id("seed", cat, day.isoformat(), title),
                    )
                )
            cursor += timedelta(days=7)
        return drafts


class AkshareCalendarEventsClient:
    """
    AkShare 财经事件客户端。

    单源超时降级，避免阻塞；失败时返回空列表由上层 seed 兜底。
    """

    def __init__(self, timeout: float = 6.0) -> None:
        self.timeout = timeout

    def fetch(self, start: date, end: date) -> list[EventDraft]:
        """聚合百度财经日历、财联社快讯、解禁摘要等。"""
        drafts: list[EventDraft] = []
        drafts.extend(self._economic_baidu(start, end))
        drafts.extend(self._global_news())
        drafts.extend(self._lockup_summary(start, end))
        drafts.extend(self._company_events(start, end))
        return drafts

    def _economic_baidu(self, start: date, end: date) -> list[EventDraft]:
        """按日拉取百度财经日历（采样：今天起每周一天，最多 8 天）。"""
        try:
            import akshare as ak  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            logger.warning("akshare unavailable for economic calendar: %s", exc)
            return []

        out: list[EventDraft] = []
        days: list[date] = []
        d = start
        while d <= end and len(days) < 8:
            days.append(d)
            d += timedelta(days=7)
        for day in days:
            key = day.strftime("%Y%m%d")
            try:
                df = _call_timeout(ak.news_economic_baidu, self.timeout, date=key)
            except (FuturesTimeout, Exception) as exc:  # noqa: BLE001
                logger.info("news_economic_baidu skip %s: %s", key, exc)
                continue
            if df is None or getattr(df, "empty", True):
                continue
            for idx, row in df.head(40).iterrows():
                title = _pick(row, ("事件", "指标", "title", "名称")) or "财经事件"
                region = _pick(row, ("地区", "国家", "region")) or "CN"
                importance = _importance_from_stars(_pick(row, ("重要性", "星级", "重要")))
                tm = _pick(row, ("时间", "公布时间", "time")) or ""
                summary = _pick(row, ("前值", "预期", "公布", "解读")) or ""
                out.append(
                    EventDraft(
                        event_date=day,
                        event_time=str(tm)[:16],
                        category="macro",
                        importance=importance,
                        title=str(title)[:256],
                        summary=str(summary)[:1000],
                        region=str(region)[:16] or "CN",
                        source="akshare_baidu",
                        external_id=_ext_id("akshare_baidu", key, title, idx),
                        payload={"raw_keys": list(getattr(row, "index", []))},
                    )
                )
        return out

    def _global_news(self) -> list[EventDraft]:
        """当日财联社/东财全球资讯 → news。"""
        try:
            import akshare as ak  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return []
        out: list[EventDraft] = []
        today = date.today()
        for source_name, fn_name in (
            ("akshare_cls", "stock_info_global_cls"),
            ("akshare_em", "stock_info_global_em"),
        ):
            fn = getattr(ak, fn_name, None)
            if not fn:
                continue
            try:
                df = _call_timeout(fn, self.timeout)
            except (FuturesTimeout, Exception) as exc:  # noqa: BLE001
                logger.info("%s skip: %s", fn_name, exc)
                continue
            if df is None or getattr(df, "empty", True):
                continue
            for idx, row in df.head(30).iterrows():
                title = _pick(row, ("标题", "title", "内容", "快讯")) or "市场快讯"
                summary = _pick(row, ("内容", "摘要", "正文", "summary")) or str(title)
                tm = _pick(row, ("发布时间", "时间", "time")) or ""
                out.append(
                    EventDraft(
                        event_date=today,
                        event_time=str(tm)[-8:][:16] if tm else "",
                        category="news",
                        importance=4 if idx < 8 else 3,
                        title=str(title)[:256],
                        summary=str(summary)[:1000],
                        region="GLOBAL",
                        source=source_name,
                        external_id=_ext_id(source_name, today.isoformat(), title, idx),
                    )
                )
        return out

    def _lockup_summary(self, start: date, end: date) -> list[EventDraft]:
        """限售解禁摘要。"""
        try:
            import akshare as ak  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return []
        fn = getattr(ak, "stock_restricted_release_summary_em", None)
        if not fn:
            return []
        try:
            df = _call_timeout(
                fn,
                self.timeout,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        except (FuturesTimeout, Exception) as exc:  # noqa: BLE001
            logger.info("lockup summary skip: %s", exc)
            return []
        if df is None or getattr(df, "empty", True):
            return []
        out: list[EventDraft] = []
        for idx, row in df.head(80).iterrows():
            day = _parse_date(_pick(row, ("解禁时间", "解禁日", "日期", "date")))
            if day is None or day < start or day > end:
                continue
            code = _pick(row, ("代码", "股票代码", "symbol")) or ""
            name = _pick(row, ("名称", "股票简称", "name")) or ""
            title = f"{name or code} 限售解禁"
            summary = _pick(row, ("解禁市值", "解禁数量", "占比")) or "关注解禁抛压"
            out.append(
                EventDraft(
                    event_date=day,
                    category="lockup",
                    importance=3,
                    title=str(title)[:256],
                    summary=str(summary)[:1000],
                    symbol=str(code)[:16],
                    name=str(name)[:64],
                    source="akshare_lockup",
                    external_id=_ext_id("akshare_lockup", day.isoformat(), code, idx),
                )
            )
        return out

    def _company_events(self, start: date, end: date) -> list[EventDraft]:
        """东财公司大事（采样若干日）。"""
        try:
            import akshare as ak  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return []
        fn = getattr(ak, "stock_gsrl_gsdt_em", None)
        if not fn:
            return []
        out: list[EventDraft] = []
        d = start
        sampled = 0
        while d <= end and sampled < 10:
            key = d.strftime("%Y%m%d")
            try:
                df = _call_timeout(fn, self.timeout, date=key)
            except (FuturesTimeout, Exception):
                d += timedelta(days=3)
                continue
            sampled += 1
            if df is not None and not getattr(df, "empty", True):
                for idx, row in df.head(25).iterrows():
                    title = _pick(row, ("事件类型", "具体事项", "标题", "title")) or "公司大事"
                    name = _pick(row, ("简称", "名称", "name")) or ""
                    code = _pick(row, ("代码", "symbol")) or ""
                    summary = _pick(row, ("具体事项", "内容", "摘要")) or ""
                    out.append(
                        EventDraft(
                            event_date=d,
                            category="catalyst",
                            importance=3,
                            title=f"{name} {title}".strip()[:256],
                            summary=str(summary)[:1000],
                            symbol=str(code)[:16],
                            name=str(name)[:64],
                            source="akshare_gsrl",
                            external_id=_ext_id("akshare_gsrl", key, code, title, idx),
                        )
                    )
            d += timedelta(days=3)
        return out


def _pick(row: Any, keys: tuple[str, ...]) -> str:
    """从 Series/dict 宽松取字段。"""
    for key in keys:
        try:
            if hasattr(row, "get"):
                val = row.get(key)
            else:
                val = row[key] if key in row.index else None  # type: ignore[index]
        except Exception:  # noqa: BLE001
            val = None
        if val is not None and str(val).strip() and str(val).lower() != "nan":
            return str(val).strip()
    return ""


def _importance_from_stars(raw: str) -> int:
    """把星级/重要性映射到 1–5。"""
    if not raw:
        return 3
    s = str(raw)
    stars = s.count("★") or s.count("*")
    if stars:
        return max(1, min(5, stars))
    if "高" in s or "重要" in s:
        return 5
    if "中" in s:
        return 3
    if "低" in s:
        return 2
    try:
        return max(1, min(5, int(float(s))))
    except Exception:  # noqa: BLE001
        return 3


def _parse_date(raw: str) -> date | None:
    """解析常见日期字符串。"""
    if not raw:
        return None
    text = str(raw).strip().replace("/", "-").replace(".", "-")[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text.replace("-", "") if fmt == "%Y%m%d" else text, fmt).date()
        except Exception:  # noqa: BLE001
            continue
    try:
        return datetime.fromisoformat(text).date()
    except Exception:  # noqa: BLE001
        return None


class CalendarEventSync:
    """将外部事件写入 calendar_events（同 source 区间内先清后写）。"""

    def __init__(self, db: Session, client: CalendarEventsClient) -> None:
        self.db = db
        self.client = client

    def run(self, start: date, end: date) -> int:
        """
        同步区间事件。

        按 draft.source 分组：删除该 source 在窗口内旧行后批量插入，避免 upsert 冲突。

        @returns: 写入条数
        """
        drafts = self.client.fetch(start, end)
        if not drafts:
            return 0
        sources = {d.source for d in drafts}
        self.db.execute(
            delete(CalendarEvent).where(
                CalendarEvent.source.in_(sources),
                CalendarEvent.event_date >= start,
                CalendarEvent.event_date <= end,
            )
        )
        self.db.flush()
        seen: set[tuple[str, str]] = set()
        n = 0
        for draft in drafts:
            ext = draft.external_id or _ext_id(
                draft.source, draft.event_date.isoformat(), draft.title, draft.symbol
            )
            key = (draft.source, ext)
            if key in seen:
                continue
            seen.add(key)
            self.db.add(
                CalendarEvent(
                    event_date=draft.event_date,
                    event_time=draft.event_time,
                    category=draft.category,
                    importance=int(draft.importance),
                    title=draft.title,
                    summary=draft.summary,
                    symbol=draft.symbol,
                    name=draft.name,
                    region=draft.region,
                    source=draft.source,
                    external_id=ext,
                    payload_json=json.dumps(draft.payload or {}, ensure_ascii=False),
                )
            )
            n += 1
        self.db.flush()
        return n


class CalendarEventService:
    """财经日历查询与确保有数据。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_events(
        self,
        start: date,
        end: date,
        *,
        category: str | None = None,
        min_importance: int | None = None,
    ) -> list[dict[str, Any]]:
        """按日期区间列出事件。"""
        q = select(CalendarEvent).where(
            CalendarEvent.event_date >= start,
            CalendarEvent.event_date <= end,
        )
        if category and category != "all":
            q = q.where(CalendarEvent.category == category)
        if min_importance is not None:
            q = q.where(CalendarEvent.importance >= min_importance)
        rows = self.db.scalars(
            q.order_by(
                CalendarEvent.event_date.asc(),
                CalendarEvent.importance.desc(),
                CalendarEvent.event_time.asc(),
            )
        ).all()
        return [self._to_dict(r) for r in rows]

    def list_today_major(self, asof: date | None = None, *, min_importance: int = 4) -> list[dict[str, Any]]:
        """当日重大新闻/事件。"""
        day = asof or date.today()
        return self.list_events(day, day, min_importance=min_importance)

    def ensure_horizon(self, months: int = 3) -> dict[str, Any]:
        """
        确保今日至未来 N 个月有可读事件。

        页面加载走本地 seed（快路径）；真实源请调 ``sync()``。

        @returns: {synced, source, start, end}
        """
        today = date.today()
        end = today + timedelta(days=max(30, months * 31))
        horizon = self.list_events(today, end)
        majors = self.list_today_major(today, min_importance=4)
        if len(horizon) >= 5 and majors:
            return {
                "synced": 0,
                "source": "cache",
                "start": today.isoformat(),
                "end": end.isoformat(),
            }
        n = CalendarEventSync(self.db, SeedCalendarEventsClient()).run(today, end)
        self.db.flush()
        return {
            "synced": n,
            "source": "seed",
            "start": today.isoformat(),
            "end": end.isoformat(),
        }

    def sync(self, months: int = 3, *, prefer_seed: bool = False) -> dict[str, Any]:
        """强制同步未来 N 个月（AkShare 失败则 seed）。"""
        today = date.today()
        end = today + timedelta(days=max(30, months * 31))
        if prefer_seed:
            n = CalendarEventSync(self.db, SeedCalendarEventsClient()).run(today, end)
            self.db.flush()
            return {
                "synced": n,
                "source": "seed",
                "start": today.isoformat(),
                "end": end.isoformat(),
            }
        source = "akshare"
        try:
            n = CalendarEventSync(self.db, AkshareCalendarEventsClient()).run(today, end)
        except Exception as exc:  # noqa: BLE001
            logger.warning("force sync akshare failed: %s", exc)
            n = 0
        if n == 0:
            n = CalendarEventSync(self.db, SeedCalendarEventsClient()).run(today, end)
            source = "seed"
        else:
            # 补足当日重大，避免源只有宏观没有新闻
            majors = self.list_today_major(today, min_importance=4)
            if not majors:
                CalendarEventSync(self.db, SeedCalendarEventsClient()).run(today, today)
                source = "mixed"
        self.db.flush()
        return {
            "synced": n,
            "source": source,
            "start": today.isoformat(),
            "end": end.isoformat(),
        }

    @staticmethod
    def _to_dict(row: CalendarEvent) -> dict[str, Any]:
        """序列化。"""
        return {
            "id": row.id,
            "event_date": row.event_date.isoformat(),
            "event_time": row.event_time or "",
            "category": row.category,
            "importance": row.importance,
            "title": row.title,
            "summary": row.summary or "",
            "symbol": row.symbol or "",
            "name": row.name or "",
            "region": row.region or "",
            "source": row.source,
        }
