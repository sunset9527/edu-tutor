"""仅从学生学科/年级对应的 active 知识版本检索教材证据。"""

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.embeddings import embed_query
from app.models.knowledge import KnowledgePoint
from app.models.knowledge_governance import KnowledgeSourceChunk, KnowledgeVersion, Textbook
from app.models.student import Student
from app.services.knowledge.chroma_client import get_knowledge_collection


class KnowledgeRetriever:
    def __init__(self, *, collection=None, embedder=None, session_factory=SessionLocal):
        self.collection = collection or get_knowledge_collection()
        self.embedder = embedder or embed_query
        self.session_factory = session_factory

    def retrieve(
        self,
        student_id: int,
        query: str,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> dict:
        top_k = max(1, int(top_k or settings.knowledge_retrieval_top_k))
        threshold = float(
            settings.knowledge_similarity_threshold if threshold is None else threshold
        )
        db = self.session_factory()
        try:
            student = db.get(Student, student_id)
            if not student:
                raise ValueError("学生不存在")
            active_rows = (
                db.query(KnowledgeVersion, Textbook)
                .join(Textbook, Textbook.id == KnowledgeVersion.textbook_id)
                .filter(
                    Textbook.subject == student.subject,
                    Textbook.grade == student.grade,
                    Textbook.active_version_id == KnowledgeVersion.id,
                    KnowledgeVersion.status == "active",
                )
                .order_by(KnowledgeVersion.id)
                .all()
            )
            active_versions = {version.id: (version, textbook) for version, textbook in active_rows}
            active_version_ids = list(active_versions)
            config = {
                "collection": "knowledge_vectors",
                "top_k": top_k,
                "similarity_threshold": threshold,
                "subject": student.subject,
                "grade": student.grade,
                "active_version_ids": active_version_ids,
            }
            if not active_version_ids:
                return {
                    "student_id": student.id,
                    "query": query,
                    "active_version_ids": [],
                    "candidates": [],
                    "retrieval_config": config,
                }

            hits = self.collection.query(
                query_embeddings=[self.embedder(query)],
                n_results=max(top_k * 3, top_k),
                where={"version_id": {"$in": active_version_ids}},
                include=["documents", "metadatas", "distances"],
            )
            ids = (hits.get("ids") or [[]])[0] or []
            distances = (hits.get("distances") or [[]])[0] or []
            candidates: list[dict] = []
            seen_ids: set[int] = set()
            for index, raw_id in enumerate(ids):
                try:
                    point_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if point_id in seen_ids:
                    continue
                point = db.get(KnowledgePoint, point_id)
                if (
                    not point
                    or point.version_id not in active_versions
                    or point.subject != student.subject
                    or point.grade != student.grade
                ):
                    continue
                version, textbook = active_versions[point.version_id]
                chunk = (
                    db.get(KnowledgeSourceChunk, point.source_chunk_id)
                    if point.source_chunk_id is not None
                    else None
                )
                if chunk is not None and chunk.version_id != version.id:
                    chunk = None
                distance = float(distances[index]) if index < len(distances) else 1.0
                similarity = round(max(0.0, min(1.0, 1.0 - distance)), 6)
                content = point.content_md or ""
                legacy = bool(point.provenance_gap or textbook.source_kind == "legacy")
                candidates.append(
                    {
                        "knowledge_point_id": point.id,
                        "title": point.title,
                        "content": content,
                        "difficulty": point.difficulty,
                        "chapter": point.chapter,
                        "version_id": version.id,
                        "version_no": version.version_no,
                        "source_chunk_id": chunk.id if chunk else None,
                        "page_range": [chunk.start_page, chunk.end_page] if chunk else None,
                        "source_excerpt": point.source_excerpt,
                        "similarity": similarity,
                        "adopted": similarity >= threshold and bool(content.strip()),
                        "legacy": legacy,
                        "textbook": {
                            "id": textbook.id,
                            "filename": textbook.original_filename,
                            "publisher": textbook.publisher,
                            "edition": textbook.edition,
                            "volume": textbook.volume,
                            "source_kind": textbook.source_kind,
                        },
                    }
                )
                seen_ids.add(point_id)
                if len(candidates) >= top_k:
                    break
            return {
                "student_id": student.id,
                "query": query,
                "active_version_ids": active_version_ids,
                "candidates": candidates,
                "retrieval_config": config,
            }
        finally:
            db.close()
