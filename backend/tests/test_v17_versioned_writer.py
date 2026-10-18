"""v1.7 staged 知识版本写入与向量来源 metadata。"""

import importlib.util
import uuid
from pathlib import Path

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.models.knowledge_governance import KnowledgeSourceChunk, KnowledgeVersion, Textbook


class FakeCollection:
    def __init__(self):
        self.upserts: list[dict] = []
        self.deleted: list[str] = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def delete(self, ids):
        self.deleted.extend(ids)


def _load_writer_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "knowledge"
        / "versioned_writer.py"
    )
    assert path.exists(), "应提供版本化知识写入器"
    spec = importlib.util.spec_from_file_location("versioned_writer", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_writer_links_points_to_version_source_and_vector_metadata():
    module = _load_writer_module()
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    textbook = Textbook(
        identity_key=f"writer:{token}",
        grade="初一",
        subject=f"写入测试-{token}",
        source_kind="uploaded",
    )
    db.add(textbook)
    db.flush()
    version = KnowledgeVersion(textbook_id=textbook.id, version_no=1, status="building")
    db.add(version)
    db.flush()
    chunk = KnowledgeSourceChunk(
        version_id=version.id,
        sequence=1,
        start_page=3,
        end_page=4,
        raw_text="这是来自教材第三到第四页的原始内容。",
        content_hash="a" * 64,
        parse_method="text",
        parser_version="pymupdf-test",
    )
    db.add(chunk)
    db.commit()
    collection = FakeCollection()
    writer = module.VersionedKnowledgeWriter(
        collection=collection,
        embedder=lambda texts: [[float(index)] for index, _ in enumerate(texts)],
    )
    point_ids: list[int] = []
    try:
        rows = writer.save_chunk_points(
            db,
            version_id=version.id,
            source_chunk_id=chunk.id,
            subject=textbook.subject,
            grade=textbook.grade,
            chapter="第一章",
            points=[
                {
                    "title": "基础概念",
                    "content_md": "基础概念正文",
                    "difficulty": "基础",
                    "prerequisites": [],
                    "related": ["进阶概念"],
                },
                {
                    "title": "进阶概念",
                    "content_md": "进阶概念正文",
                    "difficulty": "进阶",
                    "prerequisites": ["基础概念"],
                    "related": [],
                },
            ],
        )
        db.commit()
        point_ids = [row.id for row in rows]
        assert all(row.version_id == version.id for row in rows)
        assert all(row.source_chunk_id == chunk.id for row in rows)
        assert all(row.provenance_gap is False for row in rows)
        assert db.query(KnowledgePointLink).filter(
            KnowledgePointLink.source_kp_id.in_(point_ids),
            KnowledgePointLink.target_kp_id.in_(point_ids),
        ).count() == 2

        assert len(collection.upserts) == 1
        metadata = collection.upserts[0]["metadatas"][0]
        assert metadata["textbook_id"] == textbook.id
        assert metadata["version_id"] == version.id
        assert metadata["source_chunk_id"] == chunk.id
        assert metadata["subject"] == textbook.subject
        assert metadata["grade"] == textbook.grade
    finally:
        if point_ids:
            db.query(KnowledgePointLink).filter(
                KnowledgePointLink.source_kp_id.in_(point_ids)
            ).delete(synchronize_session=False)
            db.query(KnowledgePointLink).filter(
                KnowledgePointLink.target_kp_id.in_(point_ids)
            ).delete(synchronize_session=False)
            db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).delete(
                synchronize_session=False
            )
        db.query(KnowledgeSourceChunk).filter(
            KnowledgeSourceChunk.id == chunk.id
        ).delete()
        textbook.active_version_id = None
        db.flush()
        db.query(KnowledgeVersion).filter(KnowledgeVersion.id == version.id).delete()
        db.query(Textbook).filter(Textbook.id == textbook.id).delete()
        db.commit()
        db.close()
