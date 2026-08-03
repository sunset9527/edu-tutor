"""知识库编译管线：PDF 课本 → 知识点图谱落库

用法：
    python scripts/build_knowledge.py "<pdf路径>" --subject 数学 --grade 初一 [--limit N]

示例：
    python scripts/build_knowledge.py "E:\个人发展\002职业\项目4：个性化教育\知识库\初中\人教版数学六三制：电子课本\2024 人教版数学 七年级上册电子课本（高清正式版）.pdf" --subject 数学 --grade 初一
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.knowledge.graph_service import KnowledgeGraphService  # noqa: E402
from app.services.knowledge.pdf_parser import extract_text_by_pages, group_pages  # noqa: E402
from app.services.knowledge.wiki_compiler import WikiCompiler  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="教材 PDF → 知识点图谱")
    parser.add_argument("pdf", help="教材 PDF 路径")
    parser.add_argument("--subject", default="数学")
    parser.add_argument("--grade", default="初一")
    parser.add_argument("--group", type=int, default=12, help="每块页数（约一章内容）")
    parser.add_argument("--limit", type=int, default=0, help="只编译前 N 块（0=全部，调试用）")
    parser.add_argument("--ocr", action="store_true", help="图片版 PDF 启用 OCR（较慢）")
    args = parser.parse_args()

    pages = extract_text_by_pages(args.pdf, use_ocr=args.ocr)
    print(f"[1] 提取 {len(pages)} 页文本")

    blocks = group_pages(pages, args.group)
    if args.limit:
        blocks = blocks[: args.limit]
    print(f"[2] 分成 {len(blocks)} 个文本块")

    compiler = WikiCompiler()
    service = KnowledgeGraphService()
    total = 0
    for i, block in enumerate(blocks, 1):
        chapter = f"第{i}块(页{block['start_page']}-{block['end_page']})"
        print(f"[3.{i}] 编译 {chapter}（{len(block['text'])} 字）...")
        points = compiler.compile_chapter(
            args.subject, args.grade, chapter, block["text"]
        )
        if points:
            n = service.save_knowledge_points(
                args.subject, args.grade, chapter, points
            )
            total += n
            print(f"      -> {n} 个知识点落库")
        else:
            print(f"      -> 无知识点")

    print(f"\n[4] 完成：共 {total} 个知识点")
    stats = service.get_stats(args.subject)
    print(f"[5] 图谱统计: {stats}")


if __name__ == "__main__":
    main()
