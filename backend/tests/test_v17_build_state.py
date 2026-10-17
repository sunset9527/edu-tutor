"""v1.7 知识构建状态机、租约与幂等任务。"""

import importlib.util
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.database import SessionLocal
from app.models.knowledge_governance import (
    KnowledgeBuildEvent,
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    Textbook,
)
from app.models.user import User


def _load_service_module(filename: str):
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


def test_build_state_machine_allows_only_declared_transitions():
    state = _load_service_module("build_state.py")
    task = SimpleNamespace(status="queued", stage=None)

    state.transition_task(task, "running", stage="precheck")
    assert (task.status, task.stage) == ("running", "precheck")
    state.transition_task(task, "needs_attention", stage="compile")
    state.transition_task(task, "queued", stage=None)

    with pytest.raises(state.InvalidBuildTransition):
        state.transition_task(task, "succeeded")


def test_repository_is_idempotent_and_reclaims_expired_lease():
    repository = _load_service_module("build_repository.py")
    token = uuid.uuid4().hex[:10]
    now = datetime(2026, 10, 17, 12, 0, 0)
    db = SessionLocal()
    user = User(username=f"v17-build-{token}", password_hash="fixture", role="admin")
    textbook = Textbook(
        identity_key=f"textbook:{token}",
        school_stage="初中",
        grade="初一",
        subject=f"构建测试-{token}",
        publisher="测试出版社",
        edition="2026",
        volume="上册",
        source_kind="uploaded",
    )
    db.add_all([user, textbook])
    db.commit()
    task_id = None
    try:
        first, created = repository.create_build_task(
            db,
            textbook_id=textbook.id,
            requested_by=user.id,
            idempotency_key=f"build:{token}",
            build_config={"group_size": 12},
        )
        second, duplicate_created = repository.create_build_task(
            db,
            textbook_id=textbook.id,
            requested_by=user.id,
            idempotency_key=f"build:{token}",
            build_config={"group_size": 12},
        )
        task_id = first.id
        assert created is True and duplicate_created is False
        assert second.id == first.id

        claimed = repository.claim_next_task(
            db, worker_id="worker-a", now=now, lease_seconds=60
        )
        assert claimed.id == first.id
        assert claimed.status == "running" and claimed.lease_owner == "worker-a"
        assert (
            repository.claim_next_task(
                db,
                worker_id="worker-b",
                now=now + timedelta(seconds=30),
                lease_seconds=60,
            )
            is None
        )

        claimed.lease_expires_at = now - timedelta(seconds=1)
        db.commit()
        reclaimed = repository.claim_next_task(
            db, worker_id="worker-b", now=now, lease_seconds=60
        )
        assert reclaimed.id == first.id
        assert reclaimed.lease_owner == "worker-b"

        reclaimed.status = "needs_attention"
        reclaimed.failed_units = 1
        unit = KnowledgeBuildUnit(
            task_id=reclaimed.id,
            unit_type="extract_page",
            sequence=1,
            start_page=1,
            end_page=1,
            status="failed",
            attempts=1,
            error_type="parse_error",
            error_detail="fixture",
        )
        db.add(unit)
        db.commit()
        reset_count = repository.reset_failed_units(db, reclaimed.id)
        db.refresh(unit)
        db.refresh(reclaimed)
        assert reset_count == 1
        assert unit.status == "pending" and unit.error_type is None
        assert reclaimed.status == "queued"
        assert reclaimed.retry_count == 1 and reclaimed.failed_units == 0
    finally:
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
        textbook.active_version_id = None
        db.flush()
        db.delete(textbook)
        db.delete(user)
        db.commit()
        db.close()
