"""v1.7 PDF 来源页、文本块与解析版本。"""

import uuid
from pathlib import Path

import fitz

from app.services.knowledge import pdf_parser


def test_text_pdf_parser_preserves_page_and_block_coordinates():
    extractor = getattr(pdf_parser, "extract_page_records", None)
    assert callable(extractor), "应提供带来源坐标的 PDF 解析接口"

    data_dir = Path(__file__).resolve().parents[1] / "data" / "test_pdf"
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = data_dir / f"source-{uuid.uuid4().hex[:10]}.pdf"
    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "First page algebra")
    second = document.new_page()
    second.insert_text((72, 72), "Second page geometry")
    document.save(pdf_path)
    document.close()
    try:
        records = extractor(str(pdf_path))
        assert [record["page"] for record in records] == [1, 2]
        assert all(record["parse_method"] == "text" for record in records)
        assert all(record["parser_version"].startswith("pymupdf-") for record in records)
        assert "algebra" in records[0]["text"]
        assert records[0]["blocks"]
        assert len(records[0]["blocks"][0]["bbox"]) == 4

        compatible = pdf_parser.extract_text_by_pages(str(pdf_path))
        assert compatible == [
            {"page": record["page"], "text": record["text"]}
            for record in records
        ]
    finally:
        pdf_path.unlink()
        if data_dir.exists() and not any(data_dir.iterdir()):
            data_dir.rmdir()
