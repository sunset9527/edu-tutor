"""知识库去重：合并重复标题的知识点（分块编译的副作用）

策略：同 title 保留 content_md 最长的节点，其余删除；
- 被删节点参与的边重连到保留节点（若已存在同对边则删除）
- 记忆关联 knowledge_point_id 重指保留节点
- 同步清理 Chroma 向量
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.knowledge import KnowledgePoint, KnowledgePointLink  # noqa: E402
from app.models.memory import Memory  # noqa: E402
from app.services.knowledge.chroma_client import get_knowledge_collection  # noqa: E402
from app.services.knowledge.graph_service import KnowledgeGraphService  # noqa: E402


def main() -> None:
    db = SessionLocal()
    collection = get_knowledge_collection()
    try:
        dup_rows = (
            db.query(KnowledgePoint.title, func.count(KnowledgePoint.id))
            .group_by(KnowledgePoint.title)
            .having(func.count(KnowledgePoint.id) > 1)
            .all()
        )
        print(f"发现 {len(dup_rows)} 组重复标题")

        total_removed = 0
        for title, cnt in dup_rows:
            kps = (
                db.query(KnowledgePoint)
                .filter(KnowledgePoint.title == title)
                .order_by(KnowledgePoint.id)
                .all()
            )
            keep = max(kps, key=lambda k: len(k.content_md or ""))
            remove_ids = [k.id for k in kps if k.id != keep.id]

            for rid in remove_ids:
                # 删除被删节点参与的所有边（不重连，避免唯一约束冲突）
                db.query(KnowledgePointLink).filter(
                    KnowledgePointLink.source_kp_id == rid
                ).delete(synchronize_session=False)
                db.query(KnowledgePointLink).filter(
                    KnowledgePointLink.target_kp_id == rid
                ).delete(synchronize_session=False)

                # 记忆关联置空（不重指，避免语义错配）
                for m in db.query(Memory).filter(Memory.knowledge_point_id == rid).all():
                    m.knowledge_point_id = None

                # 删节点 + 向量
                kp = db.get(KnowledgePoint, rid)
                if kp:
                    db.delete(kp)
                try:
                    collection.delete(ids=[str(rid)])
                except Exception:  # noqa: BLE001
                    pass
                total_removed += 1

        db.commit()
        print(f"去重完成：删除 {total_removed} 个重复知识点")
        print("去重后统计:", KnowledgeGraphService().get_stats("数学"))
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"去重失败，已回滚: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
