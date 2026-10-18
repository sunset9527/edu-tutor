"""PDF 文本提取（pymupdf）"""
import logging
from importlib.metadata import version

import fitz

logger = logging.getLogger(__name__)


def extract_page_record(
    pdf_path: str, page_number: int, use_ocr: bool = False
) -> dict:
    """提取单页记录；页码从 1 开始，供可恢复 worker 使用。"""
    if page_number < 1:
        raise ValueError("页码必须从 1 开始")
    if use_ocr:
        from app.services.knowledge.ocr import ocr_pdf

        rows = ocr_pdf(pdf_path, start=page_number - 1, end=page_number)
        text = rows[0].strip() if rows else ""
        return {
            "page": page_number,
            "text": text,
            "blocks": [],
            "parse_method": "ocr",
            "parser_version": f"rapidocr-onnxruntime-{version('rapidocr-onnxruntime')}",
        }

    document = fitz.open(pdf_path)
    try:
        if page_number > document.page_count:
            raise ValueError("页码超过 PDF 总页数")
        page = document[page_number - 1]
        text = page.get_text().strip()
        blocks = []
        for block in page.get_text("blocks"):
            block_text = str(block[4]).strip()
            if block_text:
                blocks.append(
                    {
                        "bbox": [float(value) for value in block[:4]],
                        "text": block_text,
                    }
                )
        return {
            "page": page_number,
            "text": text,
            "blocks": blocks,
            "parse_method": "text",
            "parser_version": f"pymupdf-{fitz.VersionBind}",
        }
    finally:
        document.close()


def extract_page_records(pdf_path: str, use_ocr: bool = False) -> list[dict]:
    """逐页提取可追溯文本，保留解析方式、版本和文字块坐标。"""
    if use_ocr:
        document = fitz.open(pdf_path)
        try:
            page_count = document.page_count
        finally:
            document.close()
        return [
            record
            for page_number in range(1, page_count + 1)
            if (record := extract_page_record(pdf_path, page_number, use_ocr=True))["text"]
        ]

    doc = fitz.open(pdf_path)
    pages: list[dict] = []
    try:
        for i, page in enumerate(doc):
            record = extract_page_record(pdf_path, i + 1, use_ocr=False)
            if record["text"]:
                pages.append(record)
    finally:
        doc.close()
    logger.info(f"{pdf_path}: 共 {len(pages)} 页有文本")
    return pages


def extract_text_by_pages(pdf_path: str, use_ocr: bool = False) -> list[dict]:
    """兼容旧构建脚本，只返回页码与文本。"""
    return [
        {"page": row["page"], "text": row["text"]}
        for row in extract_page_records(pdf_path, use_ocr=use_ocr)
    ]


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
