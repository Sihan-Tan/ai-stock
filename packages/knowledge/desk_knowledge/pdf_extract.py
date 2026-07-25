"""PDF 文本抽取。"""

from __future__ import annotations

from pathlib import Path


def extract_pdf_text(path: str | Path) -> str:
    """用 pypdf 抽取 PDF 文字层，按页以换行拼接。

    Args:
        path: PDF 文件路径。

    Returns:
        抽取后的全文。

    Raises:
        ValueError: 无文字层（如扫描件）时提示需 OCR。
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages)
    if not text.strip():
        raise ValueError("无法抽取 PDF 文本，可能是扫描件，请先 OCR 后再上传")
    return text
