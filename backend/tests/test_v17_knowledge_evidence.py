"""v1.7 active 知识检索与证据充分性。"""

import importlib.util
import uuid
from pathlib import Path

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.models.knowledge_governance import KnowledgeSourceChunk, KnowledgeVersion, Textbook
from app.models.student import Student


class QueryCollection:
    def __init__(self, point_ids: list[int]):
        self.point_ids = point_ids
        self.queries: list[dict] = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {
            "ids": [[str(value) for value in self.point_ids]],
            "documents": [[f"vector-{value}" for value in self.point_ids]],
            "distances": [[0.08 + index * 0.05 for index, _ in enumerate(self.point_ids)]],
            "metadatas": [[{} for _ in self.point_ids]],
        }


def _load_module(filename: str):
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "knowledge"
        / filename
    )
    assert path.exists(), f"应提供 {filename}"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_retriever_only_returns_students_active_subject_and_grade():
    retriever_module = _load_module("retriever.py")
    token = uuid.uuid4().hex[:10]
    subject = f"证据学科-{token}"
    db = SessionLocal()
    student = Student(name=f"证据-{token}", grade="初一", subject=subject)
    active_book = Textbook(
        identity_key=f"evidence-active:{token}",
        grade="初一",
        subject=subject,
        publisher="证据出版社",
        original_filename="active.pdf",
        source_kind="uploaded",
    )
    staged_book = Textbook(
        identity_key=f"evidence-staged:{token}",
        grade="初一",
        subject=subject,
        original_filename="staged.pdf",
        source_kind="uploaded",
    )
    other_book = Textbook(
        identity_key=f"evidence-other:{token}",
        grade="初二",
        subject=subject,
        original_filename="other.pdf",
        source_kind="uploaded",
    )
    db.add_all([student, active_book, staged_book, other_book])
    db.flush()
    active_version = KnowledgeVersion(
        textbook_id=active_book.id, version_no=1, status="active"
    )
    staged_version = KnowledgeVersion(
        textbook_id=staged_book.id, version_no=1, status="staged"
    )
    other_version = KnowledgeVersion(
        textbook_id=other_book.id, version_no=1, status="active"
    )
    db.add_all([active_version, staged_version, other_version])
    db.flush()
    active_book.active_version_id = active_version.id
    other_book.active_version_id = other_version.id
    chunks = []
    points = []
    for index, (book, version) in enumerate(
        [
            (active_book, active_version),
            (staged_book, staged_version),
            (other_book, other_version),
        ],
        1,
    ):
        chunk = KnowledgeSourceChunk(
            version_id=version.id,
            sequence=1,
            start_page=index * 2,
            end_page=index * 2 + 1,
            raw_text=f"来源 {index}",
            content_hash=str(index) * 64,
            parse_method="text",
            parser_version="fixture",
        )
        db.add(chunk)
        db.flush()
        point = KnowledgePoint(
            subject=book.subject,
            grade=book.grade,
            chapter="第一章",
            title=f"知识点-{index}",
            slug=f"evidence-{token}-{index}",
            content_md=f"正文-{index}",
            difficulty="基础",
            version_id=version.id,
            source_chunk_id=chunk.id,
            source_excerpt=f"来源 {index}",
            provenance_gap=False,
        )
        db.add(point)
        chunks.append(chunk)
        points.append(point)
    db.commit()

    collection = QueryCollection([point.id for point in points])
    try:
        result = retriever_module.KnowledgeRetriever(
            collection=collection,
            embedder=lambda _query: [0.1, 0.2],
        ).retrieve(student.id, "一次方程怎么解", top_k=3, threshold=0.6)

        assert result["active_version_ids"] == [active_version.id]
        assert [row["knowledge_point_id"] for row in result["candidates"]] == [
            points[0].id
        ]
        candidate = result["candidates"][0]
        assert candidate["version_id"] == active_version.id
        assert candidate["source_chunk_id"] == chunks[0].id
        assert candidate["page_range"] == [2, 3]
        assert candidate["similarity"] == 0.92
        assert candidate["adopted"] is True
        assert candidate["textbook"]["publisher"] == "证据出版社"
        assert collection.queries[0]["where"] == {
            "version_id": {"$in": [active_version.id]}
        }
        assert result["retrieval_config"]["similarity_threshold"] == 0.6
    finally:
        point_ids = [row.id for row in points]
        version_ids = [active_version.id, staged_version.id, other_version.id]
        textbook_ids = [active_book.id, staged_book.id, other_book.id]
        db.query(KnowledgePointLink).filter(
            (KnowledgePointLink.source_kp_id.in_(point_ids))
            | (KnowledgePointLink.target_kp_id.in_(point_ids))
        ).delete(synchronize_session=False)
        db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).delete(
            synchronize_session=False
        )
        db.query(KnowledgeSourceChunk).filter(
            KnowledgeSourceChunk.id.in_([row.id for row in chunks])
        ).delete(synchronize_session=False)
        for book in (active_book, staged_book, other_book):
            book.active_version_id = None
        db.flush()
        db.query(KnowledgeVersion).filter(
            KnowledgeVersion.id.in_(version_ids)
        ).delete(synchronize_session=False)
        db.query(Textbook).filter(Textbook.id.in_(textbook_ids)).delete(
            synchronize_session=False
        )
        db.query(Student).filter(Student.id == student.id).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_evidence_gap_reasons_are_deterministic():
    evidence = _load_module("evidence.py")
    no_active = evidence.evaluate_knowledge_evidence(
        {"active_version_ids": [], "candidates": []}
    )
    assert no_active["evidence_gap"] is True
    assert no_active["reasons"] == ["no_active_version"]

    below = evidence.evaluate_knowledge_evidence(
        {
            "active_version_ids": [1],
            "candidates": [
                {"similarity": 0.4, "adopted": False, "content": "低分正文"}
            ],
        }
    )
    assert below["reasons"] == ["below_similarity_threshold"]

    missing = evidence.evaluate_knowledge_evidence(
        {
            "active_version_ids": [1],
            "candidates": [
                {"similarity": 0.9, "adopted": False, "content": ""}
            ],
        }
    )
    assert missing["reasons"] == ["missing_content"]

    legacy = evidence.evaluate_knowledge_evidence(
        {
            "active_version_ids": [1],
            "candidates": [
                {
                    "similarity": 0.9,
                    "adopted": True,
                    "content": "历史正文",
                    "legacy": True,
                }
            ],
        }
    )
    assert legacy["evidence_gap"] is True
    assert legacy["reasons"] == ["legacy_provenance_gap"]
