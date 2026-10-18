"""v1.7 审核、激活、并发冲突与指针回滚。"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.models.knowledge_governance import (
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    KnowledgeReview,
    KnowledgeReviewItem,
    KnowledgeSourceChunk,
    KnowledgeVersion,
    Textbook,
)
from app.models.user import User


REQUIRED_REVIEW_TYPES = ["content", "formula", "knowledge_point", "difficulty", "prerequisite"]
client = TestClient(app)


class FakeCollection:
    def __init__(self):
        self.entries: dict[str, dict] = {}

    def get(self, *, ids=None, where=None, include=None):
        version_id = (where or {}).get("version_id")
        rows = [
            (key, value)
            for key, value in self.entries.items()
            if (ids is None or key in {str(value) for value in ids})
            and (version_id is None or value["metadata"].get("version_id") == version_id)
        ]
        return {
            "ids": [key for key, _ in rows],
            "metadatas": [value["metadata"] for _, value in rows],
            "documents": [value["document"] for _, value in rows],
        }


def _load_release_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "knowledge"
        / "release_service.py"
    )
    assert path.exists(), "应提供知识版本发布服务"
    spec = importlib.util.spec_from_file_location("release_service", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_release_requires_review_and_consistency_then_can_rollback_and_reactivate():
    release = _load_release_module()
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    admin = User(username=f"v17-release-{token}", password_hash="fixture", role="admin")
    textbook = Textbook(
        identity_key=f"release:{token}",
        grade="初一",
        subject=f"发布测试-{token}",
        source_kind="uploaded",
    )
    db.add_all([admin, textbook])
    db.flush()
    old_version = KnowledgeVersion(
        textbook_id=textbook.id,
        version_no=1,
        status="active",
        created_by=admin.id,
        reviewed_by=admin.id,
        activated_by=admin.id,
    )
    staged_version = KnowledgeVersion(
        textbook_id=textbook.id,
        version_no=2,
        status="staged",
        created_by=admin.id,
    )
    db.add_all([old_version, staged_version])
    db.flush()
    textbook.active_version_id = old_version.id
    chunk = KnowledgeSourceChunk(
        version_id=staged_version.id,
        sequence=1,
        start_page=3,
        end_page=4,
        raw_text="教材正文",
        content_hash="b" * 64,
        parse_method="text",
        parser_version="fixture",
    )
    db.add(chunk)
    db.flush()
    point = KnowledgePoint(
        subject=textbook.subject,
        grade=textbook.grade,
        chapter="第一章",
        title="待发布知识点",
        slug=f"release-{token}",
        content_md="知识点正文",
        difficulty="基础",
        version_id=staged_version.id,
        source_chunk_id=chunk.id,
        source_excerpt="教材正文",
        provenance_gap=False,
    )
    db.add(point)
    db.flush()
    task = KnowledgeBuildTask(
        textbook_id=textbook.id,
        target_version_id=staged_version.id,
        requested_by=admin.id,
        idempotency_key=f"release:{token}",
        status="succeeded",
        total_units=1,
        completed_units=1,
        failed_units=0,
    )
    db.add(task)
    db.flush()
    db.add(
        KnowledgeBuildUnit(
            task_id=task.id,
            unit_type="index_chunk",
            sequence=1,
            status="completed",
        )
    )
    staged_version.point_count = 1
    staged_version.source_chunk_count = 1
    staged_version.vector_count = 1
    db.commit()

    collection = FakeCollection()
    collection.entries[str(point.id)] = {
        "document": point.content_md,
        "metadata": {
            "textbook_id": textbook.id,
            "version_id": staged_version.id,
            "source_chunk_id": chunk.id,
            "subject": textbook.subject,
            "grade": textbook.grade,
        },
    }
    try:
        with pytest.raises(release.ReleaseGateError, match="审核"):
            release.activate_version(
                db,
                version_id=staged_version.id,
                admin_id=admin.id,
                expected_active_version_id=old_version.id,
                collection=collection,
            )

        review = release.submit_review(
            db,
            version_id=staged_version.id,
            reviewer_id=admin.id,
            conclusion="passed",
            note="fixture review",
            items=[
                {
                    "item_type": item_type,
                    "target_type": "version",
                    "target_id": staged_version.id,
                    "conclusion": "pass",
                }
                for item_type in REQUIRED_REVIEW_TYPES
            ],
        )
        assert review.conclusion == "passed"

        collection.entries[str(point.id)]["metadata"]["version_id"] = old_version.id
        with pytest.raises(release.ReleaseGateError, match="metadata"):
            release.activate_version(
                db,
                version_id=staged_version.id,
                admin_id=admin.id,
                expected_active_version_id=old_version.id,
                collection=collection,
            )
        collection.entries[str(point.id)]["metadata"]["version_id"] = staged_version.id

        activated = release.activate_version(
            db,
            version_id=staged_version.id,
            admin_id=admin.id,
            expected_active_version_id=old_version.id,
            collection=collection,
        )
        assert activated.status == "active"
        db.refresh(textbook)
        db.refresh(old_version)
        assert textbook.active_version_id == staged_version.id
        assert old_version.status == "archived"
        assert str(point.id) in collection.entries

        with pytest.raises(release.ReleaseConflictError):
            release.activate_version(
                db,
                version_id=staged_version.id,
                admin_id=admin.id,
                expected_active_version_id=old_version.id,
                collection=collection,
            )

        rolled_back = release.rollback_textbook(
            db,
            textbook_id=textbook.id,
            target_version_id=old_version.id,
            admin_id=admin.id,
            expected_active_version_id=staged_version.id,
            collection=collection,
        )
        assert rolled_back.id == old_version.id
        db.refresh(textbook)
        db.refresh(staged_version)
        assert textbook.active_version_id == old_version.id
        assert staged_version.status == "archived"
        assert str(point.id) in collection.entries

        reactivated = release.activate_version(
            db,
            version_id=staged_version.id,
            admin_id=admin.id,
            expected_active_version_id=old_version.id,
            collection=collection,
        )
        assert reactivated.status == "active"
    finally:
        db.rollback()
        db.query(KnowledgeReviewItem).filter(
            KnowledgeReviewItem.review_id.in_(
                db.query(KnowledgeReview.id).filter(
                    KnowledgeReview.version_id.in_([old_version.id, staged_version.id])
                )
            )
        ).delete(synchronize_session=False)
        db.query(KnowledgeReview).filter(
            KnowledgeReview.version_id.in_([old_version.id, staged_version.id])
        ).delete(synchronize_session=False)
        db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task.id
        ).delete(synchronize_session=False)
        db.query(KnowledgeBuildTask).filter(
            KnowledgeBuildTask.id == task.id
        ).delete(synchronize_session=False)
        db.query(KnowledgePointLink).filter(
            (KnowledgePointLink.source_kp_id == point.id)
            | (KnowledgePointLink.target_kp_id == point.id)
        ).delete(synchronize_session=False)
        db.query(KnowledgePoint).filter(KnowledgePoint.id == point.id).delete(
            synchronize_session=False
        )
        db.query(KnowledgeSourceChunk).filter(
            KnowledgeSourceChunk.id == chunk.id
        ).delete(synchronize_session=False)
        textbook.active_version_id = None
        db.flush()
        db.query(KnowledgeVersion).filter(
            KnowledgeVersion.id.in_([old_version.id, staged_version.id])
        ).delete(synchronize_session=False)
        db.query(Textbook).filter(Textbook.id == textbook.id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id == admin.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_release_api_routes_require_admin_and_report_missing_version():
    token = uuid.uuid4().hex[:10]
    registered = client.post(
        "/api/auth/register",
        json={"username": f"v17-release-api-{token}", "password": "test123"},
    ).json()
    user_id = registered["user"]["id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}
    try:
        denied = client.get("/api/admin/versions/999999999", headers=headers)
        assert denied.status_code == 403

        db = SessionLocal()
        db.query(User).filter(User.id == user_id).update({"role": "admin"})
        db.commit()
        db.close()
        missing = client.get("/api/admin/versions/999999999", headers=headers)
        assert missing.status_code == 404
    finally:
        db = SessionLocal()
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
        db.close()
