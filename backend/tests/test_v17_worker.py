"""v1.7 构建 worker 的检查点、失败页组和续跑。"""

import importlib.util
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from app.core.database import SessionLocal
from app.models.knowledge_governance import (
    KnowledgeBuildEvent,
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    KnowledgeSourceChunk,
    KnowledgeVersion,
    Textbook,
)
from app.models.user import User
from app.services.knowledge import build_repository


def _load_worker_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "knowledge"
        / "build_worker.py"
    )
    assert path.exists(), "应提供持久化知识构建 worker"
    spec = importlib.util.spec_from_file_location("build_worker", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_worker_resumes_only_failed_compile_unit_and_stages_version():
    module = _load_worker_module()
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    user = User(username=f"v17-worker-{token}", password_hash="fixture", role="admin")
    textbook = Textbook(
        identity_key=f"worker:{token}",
        grade="初一",
        subject=f"worker测试-{token}",
        original_filename="fixture.pdf",
        file_path="data/fixture.pdf",
        page_count=2,
        source_kind="uploaded",
    )
    db.add_all([user, textbook])
    db.commit()
    task, _ = build_repository.create_build_task(
        db,
        textbook_id=textbook.id,
        requested_by=user.id,
        idempotency_key=f"worker:{token}",
        build_config={"group_size": 1, "use_ocr": False},
    )
    build_repository.claim_next_task(
        db,
        worker_id="worker-test",
        now=datetime(2026, 10, 17, 13, 0, 0),
        lease_seconds=300,
    )

    extraction_calls: list[int] = []
    compile_calls: list[int] = []
    index_calls: list[int] = []

    def extract_page(_path: str, page_number: int, use_ocr: bool = False):
        extraction_calls.append(page_number)
        return {
            "page": page_number,
            "text": f"第 {page_number} 页内容",
            "blocks": [],
            "parse_method": "text",
            "parser_version": "fixture-parser",
        }

    def compile_chunk(_subject, _grade, _chapter, text):
        page = 1 if "第 1 页" in text else 2
        compile_calls.append(page)
        if page == 2 and compile_calls.count(2) == 1:
            raise RuntimeError("fixture compile failure")
        return [
            {
                "title": f"知识点-{page}",
                "content_md": f"正文-{page}",
                "difficulty": "基础",
                "prerequisites": [],
                "related": [],
            }
        ]

    class FakeWriter:
        def save_chunk_points(self, _db, **kwargs):
            index_calls.append(kwargs["source_chunk_id"])
            return [SimpleNamespace(id=1000 + len(index_calls))]

    worker = module.KnowledgeBuildWorker(
        page_count_loader=lambda _path: 2,
        page_extractor=extract_page,
        compiler=compile_chunk,
        writer=FakeWriter(),
    )
    version_id = None
    try:
        first = worker.process_task(task.id, worker_id="worker-test")
        assert first["status"] == "needs_attention"
        # claim_next_task() refreshes the fixture session after committing, which
        # opens a new MySQL REPEATABLE READ transaction. End that snapshot before
        # verifying commits made by the worker's independent session.
        db.rollback()
        db.expire_all()
        failed_task = db.get(KnowledgeBuildTask, task.id)
        assert failed_task.failed_units == 1
        failed_units = db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task.id,
            KnowledgeBuildUnit.status == "failed",
        ).all()
        assert len(failed_units) == 1
        assert failed_units[0].unit_type == "compile_chunk"

        build_repository.reset_failed_units(db, task.id)
        build_repository.claim_next_task(
            db,
            worker_id="worker-test",
            now=datetime(2026, 10, 17, 13, 1, 0),
            lease_seconds=300,
        )
        second = worker.process_task(task.id, worker_id="worker-test")
        assert second["status"] == "succeeded"
        version_id = second["version_id"]
        db.rollback()
        db.expire_all()
        version = db.get(KnowledgeVersion, version_id)
        assert version.status == "staged"
        assert extraction_calls == [1, 2]
        assert compile_calls == [1, 2, 2]
        assert len(index_calls) == 2
    finally:
        db.rollback()
        version_ids = [
            row[0]
            for row in db.query(KnowledgeVersion.id)
            .filter(KnowledgeVersion.textbook_id == textbook.id)
            .all()
        ]
        db.query(KnowledgeBuildEvent).filter(
            KnowledgeBuildEvent.task_id == task.id
        ).delete(synchronize_session=False)
        db.query(KnowledgeSourceChunk).filter(
            KnowledgeSourceChunk.version_id.in_(version_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task.id
        ).delete(synchronize_session=False)
        db.query(KnowledgeBuildTask).filter(
            KnowledgeBuildTask.id == task.id
        ).delete(synchronize_session=False)
        textbook.active_version_id = None
        db.flush()
        db.query(KnowledgeVersion).filter(
            KnowledgeVersion.id.in_(version_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(Textbook).filter(Textbook.id == textbook.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.close()


def test_worker_stops_at_unit_boundary_after_cancellation():
    module = _load_worker_module()
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    user = User(username=f"v17-worker-cancel-{token}", password_hash="fixture", role="admin")
    textbook = Textbook(
        identity_key=f"worker-cancel:{token}",
        grade="初一",
        subject=f"worker取消-{token}",
        original_filename="fixture.pdf",
        file_path="data/fixture.pdf",
        page_count=2,
        source_kind="uploaded",
    )
    db.add_all([user, textbook])
    db.commit()
    task, _ = build_repository.create_build_task(
        db,
        textbook_id=textbook.id,
        requested_by=user.id,
        idempotency_key=f"worker-cancel:{token}",
        build_config={"group_size": 1, "use_ocr": False},
    )
    build_repository.claim_next_task(
        db,
        worker_id="worker-cancel-test",
        now=datetime(2026, 10, 17, 14, 0, 0),
        lease_seconds=300,
    )
    extraction_calls: list[int] = []

    def extract_and_cancel(_path: str, page_number: int, use_ocr: bool = False):
        extraction_calls.append(page_number)
        cancel_db = SessionLocal()
        try:
            build_repository.cancel_task(cancel_db, task.id)
        finally:
            cancel_db.close()
        return {
            "page": page_number,
            "text": f"第 {page_number} 页内容",
            "blocks": [],
            "parse_method": "text",
            "parser_version": "fixture-parser",
        }

    worker = module.KnowledgeBuildWorker(
        page_count_loader=lambda _path: 2,
        page_extractor=extract_and_cancel,
        compiler=lambda *_args: [],
    )
    try:
        result = worker.process_task(task.id, worker_id="worker-cancel-test")
        assert result["status"] == "cancelled"
        assert extraction_calls == [1]
        verify_db = SessionLocal()
        try:
            assert verify_db.get(KnowledgeBuildTask, task.id).status == "cancelled"
            assert (
                verify_db.query(KnowledgeVersion)
                .filter(KnowledgeVersion.textbook_id == textbook.id)
                .one()
                .status
                == "building"
            )
        finally:
            verify_db.close()
    finally:
        db.rollback()
        version_ids = [
            row[0]
            for row in db.query(KnowledgeVersion.id)
            .filter(KnowledgeVersion.textbook_id == textbook.id)
            .all()
        ]
        db.query(KnowledgeBuildEvent).filter(
            KnowledgeBuildEvent.task_id == task.id
        ).delete(synchronize_session=False)
        db.query(KnowledgeSourceChunk).filter(
            KnowledgeSourceChunk.version_id.in_(version_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id == task.id
        ).delete(synchronize_session=False)
        db.query(KnowledgeBuildTask).filter(
            KnowledgeBuildTask.id == task.id
        ).delete(synchronize_session=False)
        db.query(KnowledgeVersion).filter(
            KnowledgeVersion.id.in_(version_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(Textbook).filter(Textbook.id == textbook.id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        db.commit()
        db.close()
