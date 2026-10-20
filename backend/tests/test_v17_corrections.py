"""v1.7 纠错工单提交、审核与不可变知识修订。"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.models.knowledge_governance import (
    AnswerEvidenceLedger,
    CorrectionTicket,
    KnowledgeBuildEvent,
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    KnowledgeSourceChunk,
    KnowledgeVersion,
    Textbook,
)
from app.models.memory import Memory
from app.models.session import Message, Session as TutorSession
from app.models.student import Student
from app.models.user import User


client = TestClient(app)


def _load_service():
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "knowledge"
        / "correction_service.py"
    )
    assert path.exists(), "应提供纠错工单服务"
    spec = importlib.util.spec_from_file_location("correction_service", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _register(prefix: str) -> tuple[int, dict[str, str]]:
    payload = client.post(
        "/api/auth/register",
        json={"username": f"{prefix}-{uuid.uuid4().hex[:8]}", "password": "test123"},
    ).json()
    return payload["user"]["id"], {"Authorization": f"Bearer {payload['token']}"}


def test_user_feedback_snapshots_answer_and_admin_reject_requires_reason():
    owner_id, owner_headers = _register("v17-correction-owner")
    other_id, other_headers = _register("v17-correction-other")
    admin_id, admin_headers = _register("v17-correction-admin")
    db = SessionLocal()
    db.query(User).filter(User.id == admin_id).update({"role": "admin"})
    student = Student(user_id=owner_id, name="纠错提交", grade="初一", subject="数学")
    db.add(student)
    db.flush()
    session = TutorSession(student_id=student.id, subject=student.subject)
    db.add(session)
    db.flush()
    message = Message(session_id=session.id, role="assistant", content="原回答保持不变")
    db.add(message)
    db.flush()
    ledger = AnswerEvidenceLedger(
        student_id=student.id,
        session_id=session.id,
        assistant_message_id=message.id,
        knowledge_evidence=[],
        memory_evidence=[],
        retrieval_config={},
        evidence_gap={"evidence_gap": True},
    )
    db.add(ledger)
    db.commit()
    ticket_ids = []
    try:
        payload = {
            "assistant_message_id": message.id,
            "category": "explanation",
            "proposed_value": {"suggestion": "请补充移项变号原因"},
            "reason": "步骤解释不完整",
        }
        created = client.post("/api/corrections", json=payload, headers=owner_headers)
        assert created.status_code == 201, created.text
        ticket_id = created.json()["id"]
        ticket_ids.append(ticket_id)
        assert created.json()["status"] == "pending"
        assert created.json()["original_value"]["assistant_message"]["content"] == "原回答保持不变"
        assert client.post(
            "/api/corrections", json=payload, headers=other_headers
        ).status_code == 404
        db.expire_all()
        assert db.get(Message, message.id).content == "原回答保持不变"

        listing = client.get("/api/admin/corrections", headers=admin_headers)
        assert listing.status_code == 200
        assert any(row["id"] == ticket_id for row in listing.json()["items"])
        assert client.post(
            f"/api/admin/corrections/{ticket_id}/reject",
            json={"note": ""},
            headers=admin_headers,
        ).status_code == 422
        rejected = client.post(
            f"/api/admin/corrections/{ticket_id}/reject",
            json={"note": "现有解释正确，建议不成立"},
            headers=admin_headers,
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"

        accepted_created = client.post(
            "/api/corrections",
            json={**payload, "reason": "建议换一种解释方式"},
            headers=owner_headers,
        )
        assert accepted_created.status_code == 201, accepted_created.text
        accepted_id = accepted_created.json()["id"]
        ticket_ids.append(accepted_id)
        accepted = client.post(
            f"/api/admin/corrections/{accepted_id}/accept",
            json={"note": "已记录为解释质量建议"},
            headers=admin_headers,
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "applied"
        assert accepted.json()["result_reference"] == {
            "kind": "review_only",
            "assistant_message_id": message.id,
        }
        db.expire_all()
        assert db.get(Message, message.id).content == "原回答保持不变"
    finally:
        db.rollback()
        if ticket_ids:
            db.query(CorrectionTicket).filter(CorrectionTicket.id.in_(ticket_ids)).delete(
                synchronize_session=False
            )
        db.query(AnswerEvidenceLedger).filter(
            AnswerEvidenceLedger.id == ledger.id
        ).delete(synchronize_session=False)
        db.query(Message).filter(Message.id == message.id).delete(
            synchronize_session=False
        )
        db.query(TutorSession).filter(TutorSession.id == session.id).delete(
            synchronize_session=False
        )
        db.query(Student).filter(Student.id == student.id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_([owner_id, other_id, admin_id])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


class FakeCollection:
    def __init__(self):
        self.entries: dict[str, dict] = {}
        self.upserts: list[dict] = []

    def get(self, *, ids, include=None):
        rows = [(str(value), self.entries[str(value)]) for value in ids]
        return {
            "ids": [key for key, _ in rows],
            "embeddings": [row["embedding"] for _, row in rows],
            "documents": [row["document"] for _, row in rows],
            "metadatas": [row["metadata"] for _, row in rows],
        }

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)
        for index, value in enumerate(kwargs["ids"]):
            self.entries[str(value)] = {
                "embedding": kwargs["embeddings"][index],
                "document": kwargs["documents"][index],
                "metadata": kwargs["metadatas"][index],
            }

    def delete(self, ids):
        for value in ids:
            self.entries.pop(str(value), None)


def test_accepting_knowledge_correction_creates_complete_staged_child_version():
    service = _load_service()
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    user = User(username=f"v17-correction-user-{token}", password_hash="fixture")
    admin = User(username=f"v17-correction-admin-{token}", password_hash="fixture", role="admin")
    db.add_all([user, admin])
    db.flush()
    student = Student(user_id=user.id, name="知识纠错", grade="初一", subject="数学")
    textbook = Textbook(
        identity_key=f"correction:{token}", grade="初一", subject="数学", source_kind="uploaded"
    )
    db.add_all([student, textbook])
    db.flush()
    version = KnowledgeVersion(textbook_id=textbook.id, version_no=1, status="active")
    db.add(version)
    db.flush()
    textbook.active_version_id = version.id
    chunks = []
    points = []
    for index in (1, 2):
        chunk = KnowledgeSourceChunk(
            version_id=version.id,
            sequence=index,
            start_page=index,
            end_page=index,
            raw_text=f"来源-{index}",
            content_hash=str(index) * 64,
            parse_method="text",
            parser_version="fixture",
        )
        db.add(chunk)
        db.flush()
        point = KnowledgePoint(
            subject="数学",
            grade="初一",
            chapter="第一章",
            title=f"知识点-{index}",
            slug=f"correction-{token}-{index}",
            content_md=f"原正文-{index}",
            difficulty="基础",
            version_id=version.id,
            source_chunk_id=chunk.id if index == 1 else None,
            source_excerpt=f"来源-{index}",
            provenance_gap=False,
        )
        db.add(point)
        chunks.append(chunk)
        points.append(point)
    db.flush()
    db.add(
        KnowledgePointLink(
            source_kp_id=points[0].id,
            target_kp_id=points[1].id,
            link_type="prerequisite",
        )
    )
    session = TutorSession(student_id=student.id, subject="数学")
    db.add(session)
    db.flush()
    message = Message(session_id=session.id, role="assistant", content="原回答")
    db.add(message)
    db.flush()
    ledger = AnswerEvidenceLedger(
        student_id=student.id,
        session_id=session.id,
        assistant_message_id=message.id,
        knowledge_evidence=[
            {
                "knowledge_point_id": points[0].id,
                "version_id": version.id,
                "adopted": True,
            }
        ],
        memory_evidence=[],
        retrieval_config={},
        evidence_gap={"evidence_gap": False},
    )
    db.add(ledger)
    db.commit()
    collection = FakeCollection()
    for point in points:
        collection.entries[str(point.id)] = {
            "embedding": [float(point.id)],
            "document": point.content_md,
            "metadata": {"version_id": version.id},
        }
    ticket = service.create_ticket(
        db,
        submitted_by=user.id,
        category="knowledge",
        assistant_message_id=message.id,
        proposed_value={"content_md": "修订后的正文"},
        reason="原知识解释有误",
    )
    try:
        applied = service.accept_ticket(
            db,
            ticket_id=ticket.id,
            admin_id=admin.id,
            note="接受知识纠错",
            collection=collection,
            embedder=lambda texts: [[9.9] for _ in texts],
        )
        assert applied.status == "applied"
        assert applied.applied_version_id is not None
        child = db.get(KnowledgeVersion, applied.applied_version_id)
        assert child.status == "staged"
        assert child.parent_version_id == version.id
        db.refresh(textbook)
        assert textbook.active_version_id == version.id
        child_points = (
            db.query(KnowledgePoint)
            .filter(KnowledgePoint.version_id == child.id)
            .order_by(KnowledgePoint.id)
            .all()
        )
        assert len(child_points) == 2
        assert child_points[0].content_md == "修订后的正文"
        assert child_points[1].content_md == "原正文-2"
        assert points[0].content_md == "原正文-1"
        assert db.query(KnowledgePointLink).filter(
            KnowledgePointLink.source_kp_id.in_([row.id for row in child_points])
        ).count() == 1
        assert len(collection.upserts) == 1
    finally:
        db.rollback()
        all_version_ids = [
            row[0]
            for row in db.query(KnowledgeVersion.id)
            .filter(KnowledgeVersion.textbook_id == textbook.id)
            .all()
        ]
        all_point_ids = [
            row[0]
            for row in db.query(KnowledgePoint.id)
            .filter(KnowledgePoint.version_id.in_(all_version_ids))
            .all()
        ]
        task_ids = [
            row[0]
            for row in db.query(KnowledgeBuildTask.id)
            .filter(KnowledgeBuildTask.textbook_id == textbook.id)
            .all()
        ]
        db.query(KnowledgeBuildEvent).filter(
            KnowledgeBuildEvent.task_id.in_(task_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(KnowledgeBuildUnit).filter(
            KnowledgeBuildUnit.task_id.in_(task_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(KnowledgeBuildTask).filter(
            KnowledgeBuildTask.id.in_(task_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(KnowledgePointLink).filter(
            (KnowledgePointLink.source_kp_id.in_(all_point_ids or [-1]))
            | (KnowledgePointLink.target_kp_id.in_(all_point_ids or [-1]))
        ).delete(synchronize_session=False)
        db.query(KnowledgePoint).filter(
            KnowledgePoint.id.in_(all_point_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(KnowledgeSourceChunk).filter(
            KnowledgeSourceChunk.version_id.in_(all_version_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(CorrectionTicket).filter(CorrectionTicket.id == ticket.id).delete(
            synchronize_session=False
        )
        db.query(AnswerEvidenceLedger).filter(
            AnswerEvidenceLedger.id == ledger.id
        ).delete(synchronize_session=False)
        db.query(Message).filter(Message.id == message.id).delete(
            synchronize_session=False
        )
        db.query(TutorSession).filter(TutorSession.id == session.id).delete(
            synchronize_session=False
        )
        textbook.active_version_id = None
        db.flush()
        db.query(KnowledgeVersion).filter(
            KnowledgeVersion.id.in_(all_version_ids or [-1])
        ).update({KnowledgeVersion.parent_version_id: None}, synchronize_session=False)
        db.flush()
        db.query(KnowledgeVersion).filter(
            KnowledgeVersion.id.in_(all_version_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(Textbook).filter(Textbook.id == textbook.id).delete(
            synchronize_session=False
        )
        db.query(Student).filter(Student.id == student.id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_([user.id, admin.id])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_apply_failure_keeps_ticket_accepted_for_retry():
    service = _load_service()
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    user = User(username=f"v17-correction-failure-user-{token}", password_hash="fixture")
    admin = User(
        username=f"v17-correction-failure-admin-{token}",
        password_hash="fixture",
        role="admin",
    )
    db.add_all([user, admin])
    db.flush()
    ticket = CorrectionTicket(
        category="memory",
        target_type="memory",
        target_id=999999999,
        original_value={"fixture": True},
        proposed_value={"content": "修订"},
        reason="fixture failure",
        status="pending",
        submitted_by=user.id,
    )
    db.add(ticket)
    db.commit()

    def fail_apply(_db, _ticket):
        raise RuntimeError("controlled apply failure")

    try:
        with pytest.raises(service.CorrectionApplyError, match="controlled apply failure"):
            service.accept_ticket(
                db,
                ticket_id=ticket.id,
                admin_id=admin.id,
                note="接受但应用失败",
                memory_applier=fail_apply,
            )
        db.expire_all()
        persisted = db.get(CorrectionTicket, ticket.id)
        assert persisted.status == "accepted"
        assert persisted.result_reference["kind"] == "apply_failed"
        assert "controlled apply failure" in persisted.result_reference["error"]
    finally:
        db.query(CorrectionTicket).filter(CorrectionTicket.id == ticket.id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_([user.id, admin.id])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_accepting_memory_correction_reuses_shared_editor_and_records_diff(monkeypatch):
    service = _load_service()
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    user = User(username=f"v17-correction-memory-user-{token}", password_hash="fixture")
    admin = User(
        username=f"v17-correction-memory-admin-{token}",
        password_hash="fixture",
        role="admin",
    )
    db.add_all([user, admin])
    db.flush()
    student = Student(user_id=user.id, name="记忆纠错", grade="初一", subject="数学")
    db.add(student)
    db.flush()
    memory = Memory(
        student_id=student.id,
        memory_type="semantic",
        content="旧记忆",
        mastery="基本会",
        status="active",
    )
    db.add(memory)
    db.flush()
    ticket = CorrectionTicket(
        category="memory",
        target_type="memory",
        target_id=memory.id,
        original_value={"fixture": True},
        proposed_value={"content": "已核实的新记忆", "mastery": "熟练"},
        reason="记忆内容需要修订",
        status="pending",
        submitted_by=user.id,
    )
    db.add(ticket)
    db.commit()
    vector_updates = []
    monkeypatch.setattr(
        "app.services.memory.editor.upsert_memory_vector",
        lambda row: vector_updates.append((row.id, row.content)),
    )
    try:
        applied = service.accept_ticket(
            db,
            ticket_id=ticket.id,
            admin_id=admin.id,
            note="接受记忆修订",
        )
        assert applied.status == "applied"
        assert applied.result_reference == {
            "before": {
                "content": "旧记忆",
                "mastery": "基本会",
                "status": "active",
            },
            "after": {
                "content": "已核实的新记忆",
                "mastery": "熟练",
                "status": "active",
            },
        }
        db.refresh(memory)
        assert memory.content == "已核实的新记忆"
        assert memory.mastery == "熟练"
        assert vector_updates == [(memory.id, "已核实的新记忆")]
    finally:
        db.query(CorrectionTicket).filter(CorrectionTicket.id == ticket.id).delete(
            synchronize_session=False
        )
        db.query(Memory).filter(Memory.id == memory.id).delete(synchronize_session=False)
        db.query(Student).filter(Student.id == student.id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_([user.id, admin.id])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()
