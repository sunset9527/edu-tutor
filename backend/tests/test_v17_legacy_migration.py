"""现有知识点必须幂等迁移为明确的 legacy 版本。"""

import importlib.util
import uuid
from pathlib import Path

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint
from app.models.knowledge_governance import KnowledgeVersion, Textbook


def _load_backfill_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "backfill_legacy_knowledge.py"
    assert script.exists(), "应提供 legacy 知识回填脚本"
    spec = importlib.util.spec_from_file_location("backfill_legacy_knowledge", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_legacy_backfill_is_idempotent_and_does_not_invent_provenance():
    module = _load_backfill_module()
    token = uuid.uuid4().hex[:10]
    subject = f"legacy科目-{token}"
    db = SessionLocal()
    points = [
        KnowledgePoint(
            subject=subject,
            grade="初一",
            chapter="历史章",
            title=f"历史点-{index}",
            slug=f"legacy-{token}-{index}",
            content_md=f"历史内容 {index}",
            difficulty="基础",
        )
        for index in range(2)
    ]
    db.add_all(points)
    db.commit()
    point_ids = [point.id for point in points]
    try:
        first = module.backfill_legacy_knowledge(db, point_ids=point_ids)
        db.commit()
        second = module.backfill_legacy_knowledge(db, point_ids=point_ids)
        db.commit()

        rows = db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()
        assert first["points_linked"] == 2
        assert second["points_linked"] == 0
        assert len({row.version_id for row in rows}) == 1
        assert all(row.provenance_gap for row in rows)
        assert all(row.source_chunk_id is None and row.source_excerpt is None for row in rows)
        version = db.get(KnowledgeVersion, rows[0].version_id)
        textbook = db.get(Textbook, version.textbook_id)
        assert version.status == "active"
        assert textbook.source_kind == "legacy"
        assert textbook.file_path is None and textbook.file_sha256 is None
    finally:
        rows = db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()
        version_ids = {row.version_id for row in rows if row.version_id}
        textbook_ids = {
            db.get(KnowledgeVersion, version_id).textbook_id
            for version_id in version_ids
            if db.get(KnowledgeVersion, version_id)
        }
        db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).delete(
            synchronize_session=False
        )
        for textbook_id in textbook_ids:
            textbook = db.get(Textbook, textbook_id)
            if textbook:
                textbook.active_version_id = None
        db.flush()
        if version_ids:
            db.query(KnowledgeVersion).filter(KnowledgeVersion.id.in_(version_ids)).delete(
                synchronize_session=False
            )
        if textbook_ids:
            db.query(Textbook).filter(Textbook.id.in_(textbook_ids)).delete(
                synchronize_session=False
            )
        db.commit()
        db.close()
