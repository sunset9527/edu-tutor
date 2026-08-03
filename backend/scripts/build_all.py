"""批量知识库编译：目录下全部 PDF → 知识点图谱

用法：
    python scripts/build_all.py "<PDF目录>" --subject 数学 [--ocr] [--limit N]

特性：
- 自动从文件名提取年级（一年级~六年级 / 初一~初三 / 高一~高三）与上下册
- 幂等：已编译过的（subject+grade）自动跳过
- --ocr：图片版 PDF 走 OCR（较慢）
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.knowledge import KnowledgePoint  # noqa: E402
from app.services.knowledge.graph_service import KnowledgeGraphService  # noqa: E402
from app.services.knowledge.pdf_parser import extract_text_by_pages, group_pages  # noqa: E402
from app.services.knowledge.wiki_compiler import WikiCompiler  # noqa: E402

GRADE_PATTERNS = [
    (re.compile(r"一年级"), "一年级"),
    (re.compile(r"二年级"), "二年级"),
    (re.compile(r"三年级"), "三年级"),
    (re.compile(r"四年级"), "四年级"),
    (re.compile(r"五年级"), "五年级"),
    (re.compile(r"六年级"), "六年级"),
    (re.compile(r"七年级|初一"), "初一"),
    (re.compile(r"八年级|初二"), "初二"),
    (re.compile(r"九年级|初三"), "初三"),
    (re.compile(r"高一|必修第一|必修一"), "高一"),
    (re.compile(r"高二|必修第二|必修二"), "高二"),
    (re.compile(r"高三|选修"), "高三"),
]


def guess_grade(filename: str) -> str:
    for pat, grade in GRADE_PATTERNS:
        if pat.search(filename):
            return grade
    return "未知"


def guess_subject(folder_name: str) -> str:
    for subj in ["数学", "语文", "英语", "物理", "化学", "生物", "历史", "地理", "政治", "科学", "音乐", "美术", "书法", "体育", "道法", "艺术"]:
        if subj in folder_name:
            return subj
    return "未知"


def already_built(subject: str, grade: str) -> bool:
    db = SessionLocal()
    try:
        return db.query(KnowledgePoint).filter(
            KnowledgePoint.subject == subject,
            KnowledgePoint.grade == grade,
        ).first() is not None
    finally:
        db.close()


def build_one(pdf: Path, subject: str, ocr: bool, limit: int) -> int:
    grade = guess_grade(pdf.name)
    if grade == "未知":
        print(f"  !! 无法识别年级，跳过: {pdf.name}")
        return 0
    if already_built(subject, grade):
        print(f"  == 已编译（{subject}/{grade}），跳过: {pdf.name}")
        return 0

    print(f"\n>>> 开始编译: {pdf.name} ({subject}/{grade})")
    t0 = time.time()
    pages = extract_text_by_pages(str(pdf), use_ocr=False)
    total_text = sum(len(p.get("text", "")) for p in pages)
    if total_text < 500 and ocr:
        print(f"  [1] 文本不足（{total_text} 字），启用 OCR 重试...")
        pages = extract_text_by_pages(str(pdf), use_ocr=True)
        total_text = sum(len(p.get("text", "")) for p in pages)
    print(f"  [1] 提取 {len(pages)} 页文本（{total_text} 字）")
    if total_text < 500:
        print("  !! 无文本（图片版且未启用 OCR 或 OCR 失败），跳过")
        return 0

    blocks = group_pages(pages, 12)
    if limit:
        blocks = blocks[:limit]
    compiler = WikiCompiler()
    service = KnowledgeGraphService()
    total = 0
    for i, block in enumerate(blocks, 1):
        chapter = f"第{i}块(页{block['start_page']}-{block['end_page']})"
        points = compiler.compile_chapter(subject, grade, chapter, block["text"])
        if points:
            n = service.save_knowledge_points(subject, grade, chapter, points)
            total += n
            print(f"  [3.{i}] {chapter}: +{n}")
    print(f"  [完成] {subject}/{grade}: {total} 知识点, 耗时 {time.time()-t0:.0f}s")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="批量编译目录下教材")
    parser.add_argument("pdf_dir", help="PDF 目录")
    parser.add_argument("--subject", default=None, help="科目（默认从目录名推断）")
    parser.add_argument("--ocr", action="store_true", help="图片版 PDF 走 OCR")
    parser.add_argument("--limit", type=int, default=0, help="每册只编译前 N 块（调试用）")
    parser.add_argument("--force", action="store_true", help="强制重编（跳过幂等检查）")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    subject = args.subject or guess_subject(pdf_dir.name)
    print(f"科目: {subject} | OCR: {args.ocr} | 目录: {pdf_dir}")

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    print(f"共 {len(pdfs)} 个 PDF")
    total_all = 0
    for pdf in pdfs:
        if not args.force and already_built(subject, guess_grade(pdf.name)):
            print(f"  == 已编译，跳过: {pdf.name}")
            continue
        total_all += build_one(pdf, subject, args.ocr, args.limit)
    print(f"\n全部完成：{subject} 新增 {total_all} 知识点")


if __name__ == "__main__":
    main()
