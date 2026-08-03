"""PDF OCR 模块（v1.3）：图片版 PDF 逐页 OCR 提取文本"""
import logging

import fitz
from rapidocr_onnxruntime import RapidOCR

logger = logging.getLogger(__name__)

_engine: RapidOCR | None = None


def get_engine() -> RapidOCR:
    global _engine
    if _engine is None:
        logger.info("加载 RapidOCR 引擎（首次约 10-20 秒）")
        _engine = RapidOCR()
    return _engine


def ocr_pdf(pdf_path: str, start: int = 0, end: int | None = None, dpi: int = 200, log_every: int = 5) -> list[str]:
    """逐页 OCR，返回每页文本列表（页序与 PDF 一致）"""
    engine = get_engine()
    doc = fitz.open(pdf_path)
    total = len(doc)
    end = end or total
    pages: list[str] = []
    for i in range(start, min(end, total)):
        page = doc[i]
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        result, _ = engine(img_bytes)
        text = "\n".join([line[1] for line in result]) if result else ""
        pages.append(text)
        if (i - start + 1) % log_every == 0 or i == total - 1:
            logger.info(f"[OCR] 第 {i+1}/{total} 页: {len(text)} 字")
    return pages
