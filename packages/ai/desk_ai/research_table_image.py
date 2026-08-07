"""投研精选表格 PNG 渲染。"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

from desk_ai.source_label import research_source_label
from desk_common.contracts import ResearchPickItem

_BG = "#0f1419"
_HEADER_BG = "#1a2332"
_TEXT = "#e8eef5"
_LINE = "#2a3544"

_FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\msyh.ttf"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
)

_COLUMNS = (
    ("排名", 48),
    ("代码", 110),
    ("名称", 100),
    ("评分", 56),
    ("置信度", 64),
    ("买入", 140),
    ("目标", 140),
    ("止损", 90),
    ("理由", 280),
)


def wrap_rationale_lines(
    text: str,
    max_chars_per_line: int = 14,
    max_lines: int = 3,
) -> list[str]:
    """
    将理由文本按字数折行，超出时截断并加省略号。

    @param text: 原始理由
    @param max_chars_per_line: 每行最大字符数
    @param max_lines: 最多行数
    @returns: 折行后的字符串列表
    """
    raw = (text or "").strip()
    if not raw:
        return []
    if max_chars_per_line < 1 or max_lines < 1:
        return []

    capacity = max_chars_per_line * max_lines
    truncated = len(raw) > capacity
    body = raw[:capacity]

    lines: list[str] = []
    for i in range(0, len(body), max_chars_per_line):
        lines.append(body[i : i + max_chars_per_line])
        if len(lines) >= max_lines:
            break

    if truncated and lines:
        last = lines[-1]
        if max_chars_per_line == 1:
            lines[-1] = "…"
        else:
            lines[-1] = last[: max_chars_per_line - 1] + "…"
    return lines


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """
    加载中文字体，失败时回退到 Pillow 默认字体。

    @param size: 字号
    """
    for path in _FONT_CANDIDATES:
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fmt_range(low: float, high: float) -> str:
    """
    格式化价格区间（与飞书正文一致）。

    @param low: 下限
    @param high: 上限
    """
    return f"{low:.2f}–{high:.2f}"


def _fmt_price(value: float) -> str:
    """
    格式化单价。

    @param value: 价格
    """
    return f"{value:.2f}"


def _pick_cells(pick: ResearchPickItem) -> tuple[list[str], list[str]]:
    """
    生成一行单元格；理由单独返回多行文本。

    @param pick: 精选条目
    @returns: (主单元格列表, 理由折行列表)
    """
    rationale_lines = wrap_rationale_lines(pick.rationale)
    cells = [
        str(pick.rank),
        pick.symbol,
        pick.name or "",
        f"{pick.score:.0f}",
        f"{pick.confidence:.0f}",
        _fmt_range(pick.buy_low, pick.buy_high),
        _fmt_range(pick.target_low, pick.target_high),
        _fmt_price(pick.stop_loss),
        "",
    ]
    return cells, rationale_lines


def render_research_table_png(
    asof: date,
    source: str,
    picks: Sequence[ResearchPickItem],
    *,
    errors: list[str] | None = None,
) -> bytes:
    """
    将投研精选渲染为深色主题表格 PNG。

    @param asof: 业务日
    @param source: morning|closing
    @param picks: 精选列表
    @param errors: 可选错误摘要（表头下方展示）
    @returns: PNG 字节
    """
    title_font = _load_font(22)
    header_font = _load_font(15)
    cell_font = _load_font(14)
    small_font = _load_font(12)

    padding_x = 20
    padding_y = 16
    title_h = 36
    col_gap = 8
    header_h = 34
    base_row_h = 28
    line_h = 16
    table_w = sum(w for _, w in _COLUMNS) + col_gap * (len(_COLUMNS) - 1)

    row_metas: list[tuple[list[str], list[str], int]] = []
    for pick in picks:
        cells, rationale_lines = _pick_cells(pick)
        n_lines = max(1, len(rationale_lines))
        row_h = max(base_row_h, 8 + n_lines * line_h)
        row_metas.append((cells, rationale_lines, row_h))

    err_lines: list[str] = []
    if errors:
        shown = errors[:5]
        err_lines.append("异常：" + "；".join(shown))
        if len(errors) > 5:
            err_lines.append(f"…另有 {len(errors) - 5} 条错误未列出")

    err_block_h = len(err_lines) * 18 if err_lines else 0
    body_h = sum(h for _, _, h in row_metas) if row_metas else base_row_h
    img_w = padding_x * 2 + table_w
    img_h = padding_y * 2 + title_h + err_block_h + header_h + body_h + 8

    image = Image.new("RGB", (img_w, img_h), _BG)
    draw = ImageDraw.Draw(image)

    label = research_source_label(source)
    title = f"投研精选·{label}  {asof}  共 {len(picks)} 只"
    draw.text((padding_x, padding_y), title, fill=_TEXT, font=title_font)

    y = padding_y + title_h
    for msg in err_lines:
        draw.text((padding_x, y), msg, fill="#f0a0a0", font=small_font)
        y += 18

    # 表头背景
    draw.rectangle(
        [padding_x - 4, y, padding_x + table_w + 4, y + header_h],
        fill=_HEADER_BG,
    )

    x = padding_x
    for label, width in _COLUMNS:
        draw.text((x, y + 8), label, fill=_TEXT, font=header_font)
        x += width + col_gap
    y += header_h
    draw.line([(padding_x, y), (padding_x + table_w, y)], fill=_LINE, width=1)

    if not row_metas:
        draw.text((padding_x, y + 8), "暂无精选", fill=_TEXT, font=cell_font)
    else:
        for cells, rationale_lines, row_h in row_metas:
            x = padding_x
            for idx, ((_, width), text) in enumerate(zip(_COLUMNS, cells)):
                if idx == len(_COLUMNS) - 1:
                    ry = y + 6
                    if rationale_lines:
                        for line in rationale_lines:
                            draw.text((x, ry), line, fill=_TEXT, font=small_font)
                            ry += line_h
                    else:
                        draw.text((x, y + 6), "—", fill=_TEXT, font=cell_font)
                else:
                    draw.text((x, y + 6), text, fill=_TEXT, font=cell_font)
                x += width + col_gap
            y += row_h
            draw.line([(padding_x, y), (padding_x + table_w, y)], fill=_LINE, width=1)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
