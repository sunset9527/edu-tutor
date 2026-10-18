"""把编译结果写入不可变知识版本及带来源 metadata 的向量。"""

import hashlib

from sqlalchemy.orm import Session

from app.core.embeddings import embed_texts
from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.models.knowledge_governance import KnowledgeSourceChunk, KnowledgeVersion, Textbook
from app.services.knowledge.chroma_client import get_knowledge_collection


def _slug(version_id: int, chunk_id: int, title: str) -> str:
    digest = hashlib.sha256(
        f"{version_id}:{chunk_id}:{title}".encode("utf-8")
    ).hexdigest()[:12]
    return f"{title[:150]}-v{version_id}-{digest}"


class VersionedKnowledgeWriter:
    def __init__(self, *, collection=None, embedder=None):
        self.collection = collection or get_knowledge_collection()
        self.embedder = embedder or embed_texts

    def save_chunk_points(
        self,
        db: Session,
        *,
        version_id: int,
        source_chunk_id: int,
        subject: str,
        grade: str,
        chapter: str,
        points: list[dict],
    ) -> list[KnowledgePoint]:
        version = db.get(KnowledgeVersion, version_id)
        chunk = db.get(KnowledgeSourceChunk, source_chunk_id)
        if not version or not chunk or chunk.version_id != version.id:
            raise ValueError("知识版本或来源块不存在")
        if version.status != "building":
            raise ValueError("只有 building 版本可以写入")
        textbook = db.get(Textbook, version.textbook_id)
        if not textbook:
            raise ValueError("教材不存在")
        if not points:
            return []

        created: list[KnowledgePoint] = []
        vector_ids: list[str] = []
        try:
            title_to_row: dict[str, KnowledgePoint] = {}
            for item in points:
                title = str(item["title"]).strip()
                content = str(item["content_md"]).strip()
                if not title or not content:
                    raise ValueError("知识点标题和正文不能为空")
                row = KnowledgePoint(
                    subject=subject,
                    grade=grade,
                    chapter=chapter,
                    title=title,
                    slug=_slug(version.id, chunk.id, title),
                    content_md=content,
                    difficulty=item.get("difficulty", "基础"),
                    version_id=version.id,
                    source_chunk_id=chunk.id,
                    source_excerpt=chunk.raw_text[:500],
                    provenance_gap=False,
                )
                db.add(row)
                db.flush()
                created.append(row)
                title_to_row[title] = row

            for item in points:
                target = title_to_row[item["title"]]
                for prerequisite_title in item.get("prerequisites", []):
                    prerequisite = title_to_row.get(prerequisite_title)
                    if prerequisite and prerequisite.id != target.id:
                        db.add(
                            KnowledgePointLink(
                                source_kp_id=prerequisite.id,
                                target_kp_id=target.id,
                                link_type="prerequisite",
                            )
                        )
                for related_title in item.get("related", []):
                    related = title_to_row.get(related_title)
                    if related and related.id != target.id:
                        db.add(
                            KnowledgePointLink(
                                source_kp_id=target.id,
                                target_kp_id=related.id,
                                link_type="related",
                            )
                        )
            db.flush()

            documents = [row.content_md or "" for row in created]
            vector_ids = [str(row.id) for row in created]
            embeddings = self.embedder(documents)
            metadatas = [
                {
                    "textbook_id": textbook.id,
                    "version_id": version.id,
                    "source_chunk_id": chunk.id,
                    "start_page": chunk.start_page,
                    "end_page": chunk.end_page,
                    "subject": subject,
                    "grade": grade,
                    "status": version.status,
                }
                for _ in created
            ]
            self.collection.upsert(
                ids=vector_ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents,
            )
            version.point_count = (
                db.query(KnowledgePoint)
                .filter(KnowledgePoint.version_id == version.id)
                .count()
            )
            version.edge_count = (
                db.query(KnowledgePointLink)
                .join(
                    KnowledgePoint,
                    KnowledgePoint.id == KnowledgePointLink.source_kp_id,
                )
                .filter(KnowledgePoint.version_id == version.id)
                .count()
            )
            version.source_chunk_count = (
                db.query(KnowledgeSourceChunk)
                .filter(KnowledgeSourceChunk.version_id == version.id)
                .count()
            )
            version.vector_count = version.point_count
            db.flush()
            return created
        except Exception:
            db.rollback()
            if vector_ids:
                try:
                    self.collection.delete(ids=vector_ids)
                except Exception:  # noqa: BLE001
                    pass
            raise
