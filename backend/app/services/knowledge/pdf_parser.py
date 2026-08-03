"""PDF 文本提取（pymupdf）"""
import logging

import fitz

logger = logging.getLogger(__name__)


def extract_text_by_pages(pdf_path: str) -> list[dict]:
    """提取每页文本，返回 [{page, text}]（跳过空页）"""
    doc = fitz.open(pdf_path)
    pages = []
    try:
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                pages.append({"page": i + 1, "text": text})
    finally:
        doc.close()
    logger.info(f"{pdf_path}: 共 {len(pages)} 页有文本")
    return pages


def group_pages(pages: list[dict], group_size: int = 3) -> list[dict]:
    """每 N 页合成一个文本块（约一个知识点的量）"""
    blocks = []
    for i in range(0, len(pages), group_size):
        chunk = pages[i : i + group_size]
        text = "\n".join(p["text"] for p in chunk)
        blocks.append(
            {
                "start_page": chunk[0]["page"],
                "end_page": chunk[-1]["page"],
                "text": text,
            }
        )
    return blocks


def preview_pdf(pdf_path: str, max_pages: int = 3) -> None:
    """快速预览 PDF 文本提取质量"""
    pages = extract_text_by_pages(pdf_path)
    print(f"总页数（有文本）: {len(pages)}")
    for p in pages[:max_pages]:
        print(f"--- 第 {p['page']} 页（前 300 字）---")
        print(p["text"][:300])
