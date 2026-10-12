"""v1.6 会话恢复、记忆分页和真实科目 API 集成测试。"""

import uuid

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.knowledge import KnowledgePoint
from app.models.learning_event import LearningEvent
from app.models.memory import Memory, ReviewPlan
from app.models.session import Message, Session as TutorSession
from app.models.student import Student, StudentProfile
from app.models.user import User

client = TestClient(app)


def _register(prefix: str) -> tuple[int, dict[str, str]]:
    response = client.post(
        "/api/auth/register",
        json={"username": f"{prefix}-{uuid.uuid4().hex[:10]}", "password": "test123"},
    )
    data = response.json()
    return data["user"]["id"], {"Authorization": f"Bearer {data['token']}"}


def test_session_messages_restore_in_order_and_hide_cross_account():
    owner_id, owner_headers = _register("v16-session-owner")
    other_id, other_headers = _register("v16-session-other")
    db = SessionLocal()
    student = Student(
        user_id=owner_id,
        name="会话恢复测试",
        grade="初一",
        subject="数学",
    )
    db.add(student)
    db.flush()
    tutor_session = TutorSession(student_id=student.id, subject="数学")
    db.add(tutor_session)
    db.flush()
    db.add_all(
        [
            Message(session_id=tutor_session.id, role="user", content="第一问"),
            Message(session_id=tutor_session.id, role="assistant", content="第一答"),
            Message(session_id=tutor_session.id, role="user", content="第二问"),
        ]
    )
    db.commit()
    student_id, session_id = student.id, tutor_session.id
    db.close()
    try:
        response = client.get(
            f"/api/sessions/{session_id}/messages", headers=owner_headers
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["session_id"] == session_id
        assert data["student_id"] == student_id
        assert [row["content"] for row in data["messages"]] == [
            "第一问",
            "第一答",
            "第二问",
        ]
        assert client.get(
            f"/api/sessions/{session_id}/messages", headers=other_headers
        ).status_code == 404
    finally:
        db = SessionLocal()
        db.query(Message).filter(Message.session_id == session_id).delete()
        db.query(TutorSession).filter(TutorSession.id == session_id).delete()
        db.query(Student).filter(Student.id == student_id).delete()
        db.query(User).filter(User.id.in_([owner_id, other_id])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_memory_list_supports_type_filter_and_pagination():
    user_id, headers = _register("v16-memory")
    db = SessionLocal()
    student = Student(
        user_id=user_id,
        name="分页测试",
        grade="初一",
        subject="数学",
    )
    db.add(student)
    db.flush()
    for index, memory_type in enumerate(
        ["semantic", "semantic", "semantic", "episodic", "procedural"]
    ):
        db.add(
            Memory(
                student_id=student.id,
                memory_type=memory_type,
                content=f"测试记忆-{index}",
                structured_data={"predicate": "信息", "object": str(index)},
                status="active",
            )
        )
    db.commit()
    student_id = student.id
    db.close()
    try:
        response = client.get(
            f"/api/students/{student_id}/memories",
            params={"memory_type": "semantic", "page": 2, "page_size": 2},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == 3
        assert data["page"] == 2
        assert data["page_size"] == 2
        assert len(data["items"]) == 1
        assert data["items"][0]["memory_type"] == "semantic"
    finally:
        db = SessionLocal()
        db.query(Memory).filter(Memory.student_id == student_id).delete()
        db.query(StudentProfile).filter(StudentProfile.student_id == student_id).delete()
        db.query(Student).filter(Student.id == student_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()


def test_subjects_are_loaded_from_database():
    token = uuid.uuid4().hex[:8]
    db = SessionLocal()
    points = [
        KnowledgePoint(
            subject=f"验收科目甲-{token}",
            title="测试点甲",
            slug=f"v16-subject-a-{token}",
            difficulty="基础",
        ),
        KnowledgePoint(
            subject=f"验收科目乙-{token}",
            title="测试点乙",
            slug=f"v16-subject-b-{token}",
            difficulty="基础",
        ),
    ]
    db.add_all(points)
    db.commit()
    point_ids = [point.id for point in points]
    try:
        response = client.get("/api/knowledge/subjects")
        assert response.status_code == 200
        assert f"验收科目甲-{token}" in response.json()["subjects"]
        assert f"验收科目乙-{token}" in response.json()["subjects"]
    finally:
        db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def test_review_suggestion_confirmation_is_idempotent():
    user_id, headers = _register("v16-review-confirm")
    db = SessionLocal()
    student = Student(user_id=user_id, name="确认复习", grade="初一", subject="数学")
    db.add(student)
    db.flush()
    memory = Memory(
        student_id=student.id,
        memory_type="semantic",
        content="薄弱点：移项",
        structured_data={"predicate": "薄弱点", "object": "移项"},
        status="active",
    )
    db.add(memory)
    db.commit()
    student_id, memory_id = student.id, memory.id
    db.close()
    try:
        first = client.post(f"/api/memories/{memory_id}/review-plan", headers=headers)
        second = client.post(f"/api/memories/{memory_id}/review-plan", headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["created"] is True
        assert second.json()["created"] is False
        db = SessionLocal()
        assert (
            db.query(ReviewPlan)
            .filter(
                ReviewPlan.target_type == "memory",
                ReviewPlan.target_id == memory_id,
                ReviewPlan.status == "pending",
            )
            .count()
            == 1
        )
        db.close()
    finally:
        db = SessionLocal()
        db.query(ReviewPlan).filter(ReviewPlan.target_id == memory_id).delete()
        db.query(Memory).filter(Memory.id == memory_id).delete()
        db.query(StudentProfile).filter(StudentProfile.student_id == student_id).delete()
        db.query(Student).filter(Student.id == student_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()


def test_report_timeline_points_trace_back_to_learning_event_ids():
    user_id, headers = _register("v16-report-trace")
    db = SessionLocal()
    student = Student(user_id=user_id, name="报告追溯", grade="初一", subject="数学")
    db.add(student)
    db.flush()
    event = LearningEvent(
        student_id=student.id,
        event_type="wrong_question_added",
        source_type="wrong_question",
        source_id=987,
        payload={"fixture": True},
    )
    db.add(event)
    db.commit()
    student_id, event_id = student.id, event.id
    db.close()
    try:
        response = client.get(f"/api/students/{student_id}/report", headers=headers)
        assert response.status_code == 200, response.text
        point = response.json()["timeline"][0]
        assert point["wrong_added"] == 1
        assert point["event_ids"] == [event_id]
    finally:
        db = SessionLocal()
        db.query(StudentProfile).filter(StudentProfile.student_id == student_id).delete()
        db.query(Student).filter(Student.id == student_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
        db.close()
