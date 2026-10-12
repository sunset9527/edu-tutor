"""v1.4 双库事务与人工记忆管理集成测试。"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.memory import Memory, MemoryConflict, ReviewPlan
from app.models.student import Student, StudentProfile
from app.models.user import User
from app.services.memory.chroma_client import get_memory_collection
from app.services.memory.storage import MemoryStorage

client = TestClient(app)


def test_memory_edit_and_archive_keep_vector_store_consistent():
    username = f"vector-{uuid.uuid4().hex[:10]}"
    registered = client.post(
        "/api/auth/register",
        json={"username": username, "password": "test123"},
    ).json()
    user_id = registered["user"]["id"]
    headers = {"Authorization": f"Bearer {registered['token']}"}
    created = client.post(
        "/api/students",
        json={"name": "向量同步测试", "grade": "初一", "subject": "数学"},
        headers=headers,
    )
    student_id = created.json()["id"]
    memory_id = None
    collection = get_memory_collection()
    try:
        assert MemoryStorage().write(
            student_id,
            items=[
                {
                    "type": "semantic",
                    "predicate": "薄弱点",
                    "object": "整数运算",
                    "confidence": 0.9,
                }
            ],
        ) == 1
        db = SessionLocal()
        try:
            memory = (
                db.query(Memory)
                .filter(Memory.student_id == student_id)
                .order_by(Memory.id.desc())
                .first()
            )
            memory_id = memory.id
        finally:
            db.close()

        updated = client.put(
            f"/api/memories/{memory_id}",
            json={"content": "薄弱点：分数运算"},
            headers=headers,
        )
        assert updated.status_code == 200, updated.text
        vector = collection.get(ids=[str(memory_id)], include=["documents"])
        assert vector["documents"] == ["薄弱点：分数运算"]

        archived = client.delete(f"/api/memories/{memory_id}", headers=headers)
        assert archived.status_code == 200, archived.text
        assert collection.get(ids=[str(memory_id)])["ids"] == []
    finally:
        if memory_id is not None:
            collection.delete(ids=[str(memory_id)])
        db = SessionLocal()
        try:
            db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id).delete()
            db.query(Memory).filter(Memory.student_id == student_id).delete()
            db.query(StudentProfile).filter(StudentProfile.student_id == student_id).delete()
            db.query(Student).filter(Student.id == student_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()
        finally:
            db.close()


def test_memory_write_rolls_back_when_vector_write_fails():
    db = SessionLocal()
    student = Student(name="向量失败回滚测试", grade="初一", subject="数学")
    db.add(student)
    db.commit()
    db.refresh(student)
    student_id = student.id
    db.close()

    class FailingCollection:
        def upsert(self, **_kwargs):
            raise RuntimeError("vector unavailable")

    storage = MemoryStorage()
    storage.collection = FailingCollection()
    try:
        with pytest.raises(RuntimeError, match="vector unavailable"):
            storage.write(
                student_id,
                items=[
                    {
                        "type": "semantic",
                        "predicate": "薄弱点",
                        "object": "回滚测试",
                        "confidence": 0.9,
                    }
                ],
            )

        db = SessionLocal()
        try:
            assert db.query(Memory).filter(Memory.student_id == student_id).count() == 0
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            db.query(Student).filter(Student.id == student_id).delete()
            db.commit()
        finally:
            db.close()


def test_single_value_conflict_records_history_and_removes_old_vector():
    db = SessionLocal()
    student = Student(name="单值冲突测试", grade="初一", subject="数学")
    db.add(student)
    db.commit()
    db.refresh(student)
    student_id = student.id
    db.close()
    collection = get_memory_collection()
    memory_ids: list[int] = []
    try:
        storage = MemoryStorage()
        storage.write(
            student_id,
            items=[
                {
                    "type": "semantic",
                    "predicate": "学习偏好",
                    "object": "生活化例子",
                    "confidence": 0.9,
                }
            ],
        )
        storage.write(
            student_id,
            items=[
                {
                    "type": "semantic",
                    "predicate": "学习偏好",
                    "object": "图示讲解",
                    "confidence": 0.9,
                }
            ],
        )

        db = SessionLocal()
        try:
            memories = (
                db.query(Memory)
                .filter(Memory.student_id == student_id)
                .order_by(Memory.id)
                .all()
            )
            memory_ids = [memory.id for memory in memories]
            assert [memory.status for memory in memories] == ["contradicted", "active"]
            assert (
                db.query(MemoryConflict)
                .filter(MemoryConflict.student_id == student_id)
                .count()
                == 1
            )
        finally:
            db.close()

        assert collection.get(ids=[str(memory_ids[0])])["ids"] == []
        assert collection.get(ids=[str(memory_ids[1])])["ids"] == [str(memory_ids[1])]
    finally:
        if memory_ids:
            collection.delete(ids=[str(memory_id) for memory_id in memory_ids])
        db = SessionLocal()
        try:
            db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id).delete()
            db.query(MemoryConflict).filter(MemoryConflict.student_id == student_id).delete()
            db.query(Memory).filter(Memory.student_id == student_id).delete()
            db.query(StudentProfile).filter(StudentProfile.student_id == student_id).delete()
            db.query(Student).filter(Student.id == student_id).delete()
            db.commit()
        finally:
            db.close()
