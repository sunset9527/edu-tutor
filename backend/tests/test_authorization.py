"""v1.4 账号数据归属集成测试。"""

import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.knowledge import WrongQuestion
from app.models.memory import Memory, ReviewPlan
from app.models.session import Session as TutorSession
from app.models.student import Student
from app.models.user import User

client = TestClient(app)


def _register(prefix: str) -> tuple[int, dict[str, str]]:
    username = f"{prefix}-{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "test123"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return data["user"]["id"], {"Authorization": f"Bearer {data['token']}"}


def test_anonymous_student_access_is_rejected():
    assert client.get("/api/students").status_code == 401


def test_cross_account_student_resources_are_hidden():
    owner_id, owner_headers = _register("owner")
    other_id, other_headers = _register("other")
    student_id = None
    memory_id = None
    wrong_id = None
    session_id = None
    try:
        created = client.post(
            "/api/students",
            json={"name": "归属测试学生", "grade": "初一", "subject": "数学"},
            headers=owner_headers,
        )
        assert created.status_code == 201, created.text
        student_id = created.json()["id"]

        db = SessionLocal()
        try:
            memory = Memory(
                student_id=student_id,
                memory_type="semantic",
                content="薄弱点：方程",
                structured_data={"predicate": "薄弱点", "object": "方程"},
            )
            db.add(memory)
            db.flush()
            memory_id = memory.id
            db.add(
                ReviewPlan(
                    student_id=student_id,
                    target_type="memory",
                    target_id=memory.id,
                    interval_days=1,
                    next_review_at=datetime(2026, 1, 1),
                    status="pending",
                )
            )
            wrong = WrongQuestion(
                student_id=student_id,
                question_text="1+1=?",
                mastered=0,
            )
            db.add(wrong)
            tutor_session = TutorSession(student_id=student_id, subject="数学")
            db.add(tutor_session)
            db.commit()
            db.refresh(wrong)
            db.refresh(tutor_session)
            wrong_id = wrong.id
            session_id = tutor_session.id
        finally:
            db.close()

        for path in [
            f"/api/students/{student_id}",
            f"/api/students/{student_id}/profile",
            f"/api/students/{student_id}/memories",
            f"/api/students/{student_id}/wrong-questions",
            f"/api/students/{student_id}/report",
            f"/api/students/{student_id}/review-plans",
        ]:
            assert client.get(path, headers=other_headers).status_code == 404, path

        assert client.put(
            f"/api/memories/{memory_id}",
            json={"content": "篡改"},
            headers=other_headers,
        ).status_code == 404
        assert client.post(
            f"/api/memories/{memory_id}/review",
            json={"success": True},
            headers=other_headers,
        ).status_code == 404
        assert client.delete(
            f"/api/memories/{memory_id}", headers=other_headers
        ).status_code == 404
        assert client.put(
            f"/api/wrong-questions/{wrong_id}/mastered", headers=other_headers
        ).status_code == 404
        assert client.post(
            "/api/wrong-questions",
            json={"student_id": student_id, "question_text": "越权错题"},
            headers=other_headers,
        ).status_code == 404
        assert client.post(
            "/api/quiz/generate",
            json={"student_id": student_id, "subject": "数学", "count": 1},
            headers=other_headers,
        ).status_code == 404
        assert client.post(
            "/api/chat",
            json={"student_id": student_id, "message": "测试"},
            headers=other_headers,
        ).status_code == 404
        assert client.get(
            "/api/knowledge/path/1",
            params={"student_id": student_id},
            headers=other_headers,
        ).status_code == 404
        assert client.post(
            f"/api/sessions/{session_id}/end",
            headers=other_headers,
        ).status_code == 404

        mine = client.get("/api/students", headers=owner_headers)
        assert mine.status_code == 200
        assert any(row["id"] == student_id for row in mine.json())
        others = client.get("/api/students", headers=other_headers)
        assert all(row["id"] != student_id for row in others.json())
    finally:
        db = SessionLocal()
        try:
            if student_id is not None:
                db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id).delete()
                db.query(Memory).filter(Memory.student_id == student_id).delete()
                db.query(WrongQuestion).filter(WrongQuestion.student_id == student_id).delete()
                db.query(TutorSession).filter(TutorSession.student_id == student_id).delete()
                db.query(Student).filter(Student.id == student_id).delete()
            db.query(User).filter(User.id.in_([owner_id, other_id])).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()
