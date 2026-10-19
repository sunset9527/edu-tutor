"""v1.7 统一聊天准备、证据账本与读取授权。"""

import importlib.util
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.core.config import settings
from app.main import app
from app.api import chat as chat_api
from app.models.knowledge_governance import AnswerEvidenceLedger
from app.models.session import Message, Session as TutorSession
from app.models.student import Student
from app.models.user import User


client = TestClient(app)


class FakeMemoryRetriever:
    def retrieve(self, _student_id, _query):
        return {
            "profile_summary": "学习偏好：图示",
            "relevant_memories": ["薄弱点：移项"],
            "recent_events": [],
            "trace": {
                "applied_weights": {"similarity": 1.0},
                "candidates": [
                    {
                        "memory_id": 7,
                        "content": "薄弱点：移项",
                        "selected": True,
                    }
                ],
            },
        }

    def build_injection_text(self, _result):
        return "【学生画像】\n学习偏好：图示"


class FakeKnowledgeRetriever:
    def retrieve(self, _student_id, _query):
        return {
            "active_version_ids": [21],
            "candidates": [
                {
                    "knowledge_point_id": 31,
                    "title": "移项",
                    "content": "移项要改变符号。",
                    "version_id": 21,
                    "version_no": 2,
                    "source_chunk_id": 41,
                    "page_range": [12, 13],
                    "similarity": 0.91,
                    "adopted": True,
                    "legacy": False,
                    "textbook": {"id": 11, "filename": "数学上册.pdf"},
                }
            ],
            "retrieval_config": {
                "top_k": 5,
                "similarity_threshold": 0.55,
                "active_version_ids": [21],
            },
        }


def _load_orchestration():
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "chat_orchestration.py"
    )
    assert path.exists(), "应提供流式/非流式共享聊天编排"
    spec = importlib.util.spec_from_file_location("chat_orchestration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_prepare_turn_is_shared_and_knowledge_failure_degrades_with_gap():
    orchestration = _load_orchestration()
    prepared = orchestration.prepare_turn(
        student_id=1,
        user_message="移项怎么做？",
        memory_retriever=FakeMemoryRetriever(),
        knowledge_retriever=FakeKnowledgeRetriever(),
    )
    assert prepared["evidence_gap"]["evidence_gap"] is False
    assert prepared["knowledge_result"]["candidates"][0]["adopted"] is True
    assert "[来源1]" in prepared["system_context"]
    assert "学生画像" in prepared["system_context"]

    class BrokenKnowledgeRetriever:
        def retrieve(self, *_args):
            raise RuntimeError("knowledge vector unavailable")

    degraded = orchestration.prepare_turn(
        student_id=1,
        user_message="移项怎么做？",
        memory_retriever=FakeMemoryRetriever(),
        knowledge_retriever=BrokenKnowledgeRetriever(),
    )
    assert degraded["memory_result"]["profile_summary"] == "学习偏好：图示"
    assert degraded["evidence_gap"]["reasons"] == ["knowledge_retrieval_failed"]
    assert "不能声称" in degraded["system_context"]


def test_evidence_ledger_is_idempotent_and_hidden_from_other_accounts():
    orchestration = _load_orchestration()
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    owner = User(username=f"v17-evidence-owner-{token}", password_hash="fixture")
    other = User(username=f"v17-evidence-other-{token}", password_hash="fixture")
    db.add_all([owner, other])
    db.flush()
    student = Student(
        user_id=owner.id,
        name=f"证据账本-{token}",
        grade="初一",
        subject="数学",
    )
    db.add(student)
    db.flush()
    session = TutorSession(student_id=student.id, subject=student.subject)
    db.add(session)
    db.flush()
    messages = [
        Message(session_id=session.id, role="user", content="移项怎么做？"),
        Message(session_id=session.id, role="assistant", content="先看等式两边。"),
    ]
    db.add_all(messages)
    db.commit()
    prepared = orchestration.prepare_turn(
        student_id=student.id,
        user_message="移项怎么做？",
        memory_retriever=FakeMemoryRetriever(),
        knowledge_retriever=FakeKnowledgeRetriever(),
    )
    try:
        first = orchestration.record_answer_evidence(
            student_id=student.id,
            session_id=session.id,
            assistant_message_id=messages[1].id,
            prepared=prepared,
        )
        second = orchestration.record_answer_evidence(
            student_id=student.id,
            session_id=session.id,
            assistant_message_id=messages[1].id,
            prepared=prepared,
        )
        assert first["id"] == second["id"]
        verify = SessionLocal()
        assert (
            verify.query(AnswerEvidenceLedger)
            .filter(AnswerEvidenceLedger.assistant_message_id == messages[1].id)
            .count()
            == 1
        )
        verify.close()

        # Fixtures use a non-hash password, so create real API users only for auth tokens.
        owner_auth = client.post(
            "/api/auth/register",
            json={"username": f"v17-evidence-auth-owner-{token}", "password": "test123"},
        ).json()
        other_auth = client.post(
            "/api/auth/register",
            json={"username": f"v17-evidence-auth-other-{token}", "password": "test123"},
        ).json()
        auth_user_ids = [owner_auth["user"]["id"], other_auth["user"]["id"]]
        student.user_id = auth_user_ids[0]
        db.commit()
        owner_headers = {"Authorization": f"Bearer {owner_auth['token']}"}
        other_headers = {"Authorization": f"Bearer {other_auth['token']}"}

        visible = client.get(
            f"/api/knowledge/evidence/{messages[1].id}", headers=owner_headers
        )
        assert visible.status_code == 200, visible.text
        assert visible.json()["knowledge_evidence"][0]["knowledge_point_id"] == 31
        assert visible.json()["evidence_gap"]["evidence_gap"] is False
        assert client.get(
            f"/api/knowledge/evidence/{messages[1].id}", headers=other_headers
        ).status_code == 404
    finally:
        db.rollback()
        db.query(AnswerEvidenceLedger).filter(
            AnswerEvidenceLedger.assistant_message_id == messages[1].id
        ).delete(synchronize_session=False)
        db.query(Message).filter(Message.session_id == session.id).delete(
            synchronize_session=False
        )
        db.query(TutorSession).filter(TutorSession.id == session.id).delete(
            synchronize_session=False
        )
        db.query(Student).filter(Student.id == student.id).delete(
            synchronize_session=False
        )
        usernames = [
            owner.username,
            other.username,
            f"v17-evidence-auth-owner-{token}",
            f"v17-evidence-auth-other-{token}",
        ]
        db.query(User).filter(User.username.in_(usernames)).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_non_stream_chat_keeps_response_fields_and_adds_evidence(monkeypatch):
    token = uuid.uuid4().hex[:10]
    registered = client.post(
        "/api/auth/register",
        json={"username": f"v17-chat-api-{token}", "password": "test123"},
    ).json()
    user_id = registered["user"]["id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}
    db = SessionLocal()
    student = Student(
        user_id=user_id,
        name=f"非流式-{token}",
        grade="初一",
        subject="数学",
    )
    db.add(student)
    db.commit()
    previous_key = settings.deepseek_api_key
    object.__setattr__(settings, "deepseek_api_key", "sk-fixture")
    monkeypatch.setattr(
        chat_api,
        "run_chat",
        lambda **_kwargs: {
            "response": "先看等式两边。",
            "assistant_message_id": 88,
            "evidence_ledger_id": 99,
            "evidence": {
                "knowledge": [{"knowledge_point_id": 31}],
                "memory": [],
                "gap": {"evidence_gap": False, "reasons": []},
            },
        },
    )
    try:
        response = client.post(
            "/api/chat",
            json={"student_id": student.id, "message": "移项怎么做？"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["session_id"] > 0
        assert payload["response"] == "先看等式两边。"
        assert payload["assistant_message_id"] == 88
        assert payload["evidence"]["knowledge"][0]["knowledge_point_id"] == 31
    finally:
        object.__setattr__(settings, "deepseek_api_key", previous_key)
        db.rollback()
        session_ids = [
            row[0]
            for row in db.query(TutorSession.id)
            .filter(TutorSession.student_id == student.id)
            .all()
        ]
        db.query(Message).filter(Message.session_id.in_(session_ids or [-1])).delete(
            synchronize_session=False
        )
        db.query(TutorSession).filter(
            TutorSession.id.in_(session_ids or [-1])
        ).delete(synchronize_session=False)
        db.query(Student).filter(Student.id == student.id).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
        db.close()
