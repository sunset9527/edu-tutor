"""v0.3 知识引擎测试：PDF 提取 + 图谱落库/统计 + 记忆-知识点关联"""
import pytest

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint
from app.services.knowledge.graph_service import KnowledgeGraphService
from app.services.knowledge.pdf_parser import extract_text_by_pages
from app.services.memory.storage import MemoryStorage

PDF_QIYI = r"E:\个人发展\002职业\项目4：个性化教育\知识库\初中\人教版数学六三制：电子课本\2024 人教版数学 七年级上册电子课本（高清正式版）.pdf"


def test_pdf_extract_text():
    """教材 PDF 可提取文本（文字版，非扫描）"""
    pages = extract_text_by_pages(PDF_QIYI)
    assert len(pages) > 50, f"应提取大量文本页，实际 {len(pages)}"


def test_graph_save_and_stats():
    """知识点落库 + 图谱统计"""
    service = KnowledgeGraphService()
    service.save_knowledge_points(
        "数学",
        "初一",
        "测试章",
        [
            {
                "title": "测试知识点A",
                "difficulty": "基础",
                "content_md": "A 的概念与定义，$x+1=2$",
                "prerequisites": [],
                "related": ["测试知识点B"],
            },
            {
                "title": "测试知识点B",
                "difficulty": "进阶",
                "content_md": "B 的概念与定义，$y=2x$",
                "prerequisites": ["测试知识点A"],
                "related": [],
            },
        ],
    )
    stats = service.get_stats("数学")
    assert stats["nodes"] >= 2
    assert stats["edges"] >= 2
    assert 0 < stats["connect_rate"] <= 1

    # 清理测试数据（先清边 + 向量，再删节点）
    db = SessionLocal()
    try:
        from app.models.knowledge import KnowledgePointLink

        old = db.query(KnowledgePoint).filter(KnowledgePoint.chapter == "测试章").all()
        old_ids = [kp.id for kp in old]
        if old_ids:
            db.query(KnowledgePointLink).filter(
                KnowledgePointLink.source_kp_id.in_(old_ids)
            ).delete(synchronize_session=False)
            db.query(KnowledgePointLink).filter(
                KnowledgePointLink.target_kp_id.in_(old_ids)
            ).delete(synchronize_session=False)
            for kp in old:
                db.delete(kp)
                try:
                    service.collection.delete(ids=[str(kp.id)])
                except Exception:
                    pass
        db.commit()
    finally:
        db.close()


def test_memory_knowledge_link():
    """记忆写入后能关联到知识库知识点（双引擎桥）"""
    from app.core.database import SessionLocal as SL
    from app.models.student import Student

    db = SL()
    try:
        stu = Student(name="关联测试", grade="初一", subject="数学")
        db.add(stu)
        db.commit()
        db.refresh(stu)
        student_id = stu.id
    finally:
        db.close()

    storage = MemoryStorage()
    storage.write(
        student_id,
        session_id=None,
        items=[
            {"type": "semantic", "predicate": "薄弱点", "object": "正数和负数", "confidence": 0.9}
        ],
    )

    db = SL()
    try:
        from app.models.memory import Memory

        memory = (
            db.query(Memory)
            .filter(Memory.student_id == student_id)
            .order_by(Memory.id.desc())
            .first()
        )
        # 若知识库已编译（本册教材），应能关联到知识点；否则 knowledge_point_id 为 None 也接受
        from app.services.knowledge.chroma_client import get_knowledge_collection

        if get_knowledge_collection().count() > 0:
            assert memory.knowledge_point_id is not None, "知识库非空时应完成关联"
    finally:
        db.close()
