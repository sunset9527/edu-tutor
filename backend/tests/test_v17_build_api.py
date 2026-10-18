"""v1.7 构建任务 API 的权限、幂等、重试与取消。"""

import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.knowledge_governance import (
    KnowledgeBuildEvent,
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    Textbook,
)
from app.models.user import User


client = TestClient(app)


def _register(username: str) -> tuple[int, dict[str, str]]:
    payload = client.post(
        "/api/auth/register", json={"username": username, "password": "test123"}
    ).json()
    return payload["user"]["id"], {
        "Authorization": f"Bearer {payload['token']}"
    }


def test_build_api_is_admin_only_idempotent_and_controls_failures():
    token = uuid.uuid4().hex[:10]
    admin_id, admin_headers = _register(f"v17-build-api-admin-{token}")
    user_id, user_headers = _register(f"v17-build-api-user-{token}")
    db = SessionLocal()
    textbook = Textbook(
        identity_key=f"build-api:{token}",
        grade="初一",
        subject=f"构建接口-{token}",
        original_filename="fixture.pdf",
        file_path="data/fixture.pdf",
        source_kind="uploaded",
    )
    db.query(User).filter(User.id == admin_id).update({"role": "admin"})
    db.add(textbook)
    db.commit()
    task_id = None
    try:
        denied = client.post(
            f"/api/admin/textbooks/{textbook.id}/builds",
            json={"group_size": 8, "use_ocr": False},
            headers={**user_headers, "Idempotency-Key": f"build-api:{token}"},
        )
        assert denied.status_code == 403

        first = client.post(
            f"/api/admin/textbooks/{textbook.id}/builds",
            json={"group_size": 8, "use_ocr": False},
            headers={**admin_headers, "Idempotency-Key": f"build-api:{token}"},
        )
        assert first.status_code == 201, first.text
        task_id = first.json()["id"]
        assert first.json()["status"] == "queued"

        duplicate = client.post(
            f"/api/admin/textbooks/{textbook.id}/builds",
            json={"group_size": 8, "use_ocr": False},
            headers={**admin_headers, "Idempotency-Key": f"build-api:{token}"},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == task_id

        listing = client.get("/api/admin/builds", headers=admin_headers)
        assert listing.status_code == 200
        assert any(row["id"] == task_id for row in listing.json()["items"])
        detail = client.get(f"/api/admin/builds/{task_id}", headers=admin_headers)
        assert detail.status_code == 200
        assert detail.json()["build_config"]["group_size"] == 8

        db.rollback()
        task = db.get(KnowledgeBuildTask, task_id)
        task.status = "needs_attention"
        task.failed_units = 1
        failed = KnowledgeBuildUnit(
            task_id=task_id,
            unit_type="compile_chunk",
            sequence=1,
            status="failed",
            attempts=1,
            error_type="RuntimeError",
            error_detail="fixture",
        )
        db.add(failed)
        db.commit()

        retried = client.post(
            f"/api/admin/builds/{task_id}/retry-failures", headers=admin_headers
        )
        assert retried.status_code == 200, retried.text
        assert retried.json()["status"] == "queued"
        db.rollback()
        db.refresh(failed)
        assert failed.status == "pending"

        task = db.get(KnowledgeBuildTask, task_id)
        task.status = "running"
        task.lease_owner = "worker-fixture"
        task.lease_expires_at = datetime.now() + timedelta(minutes=5)
        db.commit()
        busy = client.post(f"/api/admin/builds/{task_id}/resume", headers=admin_headers)
        assert busy.status_code == 409

        db.rollback()
        task = db.get(KnowledgeBuildTask, task_id)
        task.lease_expires_at = datetime.now() - timedelta(seconds=1)
        db.commit()
        resumed = client.post(
            f"/api/admin/builds/{task_id}/resume", headers=admin_headers
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["status"] == "running"
        assert resumed.json()["lease_owner"] is None

        cancelled = client.post(
            f"/api/admin/builds/{task_id}/cancel", headers=admin_headers
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        repeated = client.post(
            f"/api/admin/builds/{task_id}/cancel", headers=admin_headers
        )
        assert repeated.status_code == 200
        assert repeated.json()["status"] == "cancelled"
    finally:
        db.rollback()
        if task_id:
            db.query(KnowledgeBuildEvent).filter(
                KnowledgeBuildEvent.task_id == task_id
            ).delete(synchronize_session=False)
            db.query(KnowledgeBuildUnit).filter(
                KnowledgeBuildUnit.task_id == task_id
            ).delete(synchronize_session=False)
            db.query(KnowledgeBuildTask).filter(
                KnowledgeBuildTask.id == task_id
            ).delete(synchronize_session=False)
        db.query(Textbook).filter(Textbook.id == textbook.id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_([admin_id, user_id])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()
