"""知识点图谱服务：落库 + 统计 + 查询

- knowledge_points 表（知识点页）
- knowledge_point_links 表（wikilinks 边：prerequisite/related）
- knowledge_vectors collection（语义检索，记忆关联用）
"""
import hashlib
import logging

from app.core.database import SessionLocal
from app.core.embeddings import embed_texts
from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.services.knowledge.chroma_client import get_knowledge_collection

logger = logging.getLogger(__name__)


def _slug(title: str, chapter: str) -> str:
    h = hashlib.md5(f"{chapter}:{title}".encode("utf-8")).hexdigest()[:6]
    return f"{title}-{h}"


class KnowledgeGraphService:
    def __init__(self):
        self.collection = get_knowledge_collection()

    def save_knowledge_points(
        self, subject: str, grade: str, chapter: str, points: list[dict]
    ) -> int:
        """落库一批知识点（幂等：同 chapter+title 先删旧）"""
        if not points:
            return 0
        db = SessionLocal()
        try:
            # 幂等：删除同章旧数据（先清外键引用：边 + 记忆关联）
            old = (
                db.query(KnowledgePoint)
                .filter(
                    KnowledgePoint.subject == subject,
                    KnowledgePoint.grade == grade,
                    KnowledgePoint.chapter == chapter,
                )
                .all()
            )
            if old:
                old_ids = [kp.id for kp in old]
                db.query(KnowledgePointLink).filter(
                    KnowledgePointLink.source_kp_id.in_(old_ids)
                ).delete(synchronize_session=False)
                db.query(KnowledgePointLink).filter(
                    KnowledgePointLink.target_kp_id.in_(old_ids)
                ).delete(synchronize_session=False)
                from app.models.memory import Memory

                for m in db.query(Memory).filter(
                    Memory.knowledge_point_id.in_(old_ids)
                ).all():
                    m.knowledge_point_id = None
                for kp in old:
                    db.delete(kp)
                    try:
                        self.collection.delete(ids=[str(kp.id)])  # 清残留向量
                    except Exception:  # noqa: BLE001
                        pass
                db.flush()

            title_to_id: dict[str, int] = {}
            for p in points:
                kp = KnowledgePoint(
                    subject=subject,
                    grade=grade,
                    chapter=chapter,
                    title=p["title"],
                    slug=_slug(p["title"], chapter),
                    content_md=p["content_md"],
                    difficulty=p.get("difficulty", "基础"),
                )
                db.add(kp)
                db.flush()
                title_to_id[p["title"]] = kp.id

                # 向量落库
                try:
                    emb = embed_texts([p["content_md"]])[0]
                    self.collection.upsert(
                        ids=[str(kp.id)],
                        embeddings=[emb],
                        metadatas=[{"subject": subject, "grade": grade}],
                        documents=[p["content_md"]],
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error(f"知识点向量写入失败 {p['title']}: {e}")

            # 边落库（wikilinks）
            for p in points:
                src_id = title_to_id.get(p["title"])
                if not src_id:
                    continue
                for pre in p.get("prerequisites", []):
                    tgt_id = title_to_id.get(pre)
                    if tgt_id and tgt_id != src_id:
                        db.add(
                            KnowledgePointLink(
                                source_kp_id=src_id,
                                target_kp_id=tgt_id,
                                link_type="prerequisite",
                            )
                        )
                for rel in p.get("related", []):
                    tgt_id = title_to_id.get(rel)
                    if tgt_id and tgt_id != src_id:
                        db.add(
                            KnowledgePointLink(
                                source_kp_id=src_id,
                                target_kp_id=tgt_id,
                                link_type="related",
                            )
                        )

            db.commit()
            logger.info(f"落库成功: {subject}/{grade}/{chapter} 共 {len(points)} 知识点")
            return len(points)
        finally:
            db.close()

    def get_stats(self, subject: str | None = None) -> dict:
        """图谱统计（毕设数据可引用）"""
        db = SessionLocal()
        try:
            query = db.query(KnowledgePoint)
            if subject:
                query = query.filter(KnowledgePoint.subject == subject)
            nodes = query.count()
            nodes_list = query.all()

            link_query = db.query(KnowledgePointLink)
            if subject:
                subj_ids = {kp.id for kp in nodes_list}
                links = [l for l in link_query.all() if l.source_kp_id in subj_ids]
            else:
                links = link_query.count()
                links = links if isinstance(links, int) else len(links)

            # 连接率：有出边的节点占比
            if subject:
                connected = {
                    l.source_kp_id for l in links
                } | {l.target_kp_id for l in links}
                connect_rate = len(connected) / nodes if nodes else 0
                return {
                    "subject": subject,
                    "nodes": nodes,
                    "edges": len(links),
                    "connect_rate": round(connect_rate, 3),
                }
            return {"nodes": nodes, "edges": links}
        finally:
            db.close()

    def get_graph(self, subject: str | None = None) -> dict:
        """图谱数据（前端 ECharts 可视化用）"""
        db = SessionLocal()
        try:
            query = db.query(KnowledgePoint)
            if subject:
                query = query.filter(KnowledgePoint.subject == subject)
            kps = query.all()
            nodes = [
                {
                    "id": kp.id,
                    "title": kp.title,
                    "chapter": kp.chapter,
                    "difficulty": kp.difficulty,
                }
                for kp in kps
            ]
            kp_ids = {kp.id for kp in kps}
            all_links = db.query(KnowledgePointLink).all()
            edges = [
                {
                    "source": l.source_kp_id,
                    "target": l.target_kp_id,
                    "type": l.link_type,
                }
                for l in all_links
                if l.source_kp_id in kp_ids and l.target_kp_id in kp_ids
            ]
            return {"nodes": nodes, "edges": edges}
        finally:
            db.close()
