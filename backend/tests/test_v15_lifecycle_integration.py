"""v1.5 记忆生命周期的 MySQL 集成测试。"""

import uuid
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint, WrongQuestion
from app.models.memory import Memory, ReviewPlan
from app.models.session import Message, Session as TutorSession
from app.models.student import Student, StudentProfile
from app.services.memory.learning_state import record_practice_result
from app.services.memory.retriever import MemoryRetriever
from app.services.memory.session_lifecycle import end_session_with_summary
from app.services.memory.storage import MemoryStorage


class RecordingCollection:
    def __init__(self):
        self.upserts = []
        self.deleted = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def delete(self, **kwargs):
        self.deleted.append(kwargs)


def _student(db, token: str) -> Student:
    student = Student(name=f"v15-{token}", grade="初一", subject="数学")
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def test_procedural_memory_activates_only_after_repeated_evidence(monkeypatch):
    db = SessionLocal()
    token = uuid.uuid4().hex[:8]
    student = _student(db, token)
    student_id = student.id
    db.close()
    collection = RecordingCollection()
    storage = MemoryStorage()
    storage.collection = collection
    monkeypatch.setattr(
        "app.services.memory.storage.settings_service.get_int",
        lambda key, default: 3 if key == "consolidation_threshold" else default,
    )
    monkeypatch.setattr(
        "app.services.memory.storage.settings_service.get_float",
        lambda _key, default: default,
    )
    item = {
        "type": "procedural",
        "predicate": "有效策略",
        "object": "先画线段图再列式",
        "confidence": 0.9,
    }
    try:
        assert storage.write(
            student_id,
            items=[item],
            source_message_id=11,
            model_name="test-model",
        ) == 1
        assert storage.write(
            student_id,
            items=[item],
            source_message_id=11,
            model_name="test-model",
        ) == 0
        for message_id in (12,):
            assert storage.write(
                student_id,
                items=[item],
                source_message_id=message_id,
                model_name="test-model",
            ) == 1
        db = SessionLocal()
        memory = db.query(Memory).filter(Memory.student_id == student_id).one()
        assert memory.status == "candidate"
        assert memory.structured_data["evidence_count"] == 2
        db.close()
        assert collection.upserts == []

        storage.write(
            student_id,
            items=[item],
            source_message_id=13,
            model_name="test-model",
        )
        db = SessionLocal()
        memory = db.query(Memory).filter(Memory.student_id == student_id).one()
        assert memory.status == "active"
        assert memory.structured_data["evidence_count"] == 3
        assert len(memory.structured_data["provenance_history"]) == 3
        assert (
            db.query(ReviewPlan)
            .filter(ReviewPlan.target_type == "memory", ReviewPlan.target_id == memory.id)
            .count()
            == 1
        )
        db.close()
        assert len(collection.upserts) == 1
    finally:
        db = SessionLocal()
        db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id).delete()
        db.query(Memory).filter(Memory.student_id == student_id).delete()
        db.query(StudentProfile).filter(StudentProfile.student_id == student_id).delete()
        db.query(Student).filter(Student.id == student_id).delete()
        db.commit()
        db.close()


def test_practice_result_updates_mastery_and_single_pending_plan(monkeypatch):
    db = SessionLocal()
    token = uuid.uuid4().hex[:8]
    student = _student(db, token)
    kp = KnowledgePoint(
        subject="数学",
        grade="初一",
        title="有理数加法",
        slug=f"v15-mastery-{token}",
        difficulty="基础",
    )
    db.add(kp)
    db.commit()
    db.refresh(kp)
    student_id, kp_id = student.id, kp.id
    db.close()
    collection = RecordingCollection()
    monkeypatch.setattr(
        "app.services.memory.learning_state.settings_service.get_int",
        lambda _key, default: default,
    )
    try:
        def add_wrong_question(transaction_db):
            wrong = WrongQuestion(
                student_id=student_id,
                knowledge_point_id=kp_id,
                question_text="1+(-2)=?",
                mastered=0,
            )
            transaction_db.add(wrong)
            transaction_db.flush()
            return wrong.id

        initial_failure = record_practice_result(
            student_id,
            kp_id,
            success=False,
            collection=collection,
            transaction_mutation=add_wrong_question,
        )
        first = record_practice_result(student_id, kp_id, success=True, collection=collection)
        second = record_practice_result(student_id, kp_id, success=True, collection=collection)
        third = record_practice_result(student_id, kp_id, success=False, collection=collection)
        assert [first["mastery"], second["mastery"], third["mastery"]] == [
            "基本会",
            "熟练",
            "基本会",
        ]
        assert initial_failure["mastery"] == "不懂"

        db = SessionLocal()
        memory = (
            db.query(Memory)
            .filter(Memory.student_id == student_id, Memory.knowledge_point_id == kp_id)
            .one()
        )
        assert memory.mastery == "基本会"
        assert memory.structured_data["last_practice_result"] == "wrong"
        assert db.get(WrongQuestion, initial_failure["transaction_result"]) is not None
        assert (
            db.query(ReviewPlan)
            .filter(
                ReviewPlan.student_id == student_id,
                ReviewPlan.target_type == "knowledge_point",
                ReviewPlan.target_id == kp_id,
                ReviewPlan.status == "pending",
            )
            .count()
            == 1
        )
        db.close()
    finally:
        db = SessionLocal()
        db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id).delete()
        db.query(Memory).filter(Memory.student_id == student_id).delete()
        db.query(WrongQuestion).filter(WrongQuestion.student_id == student_id).delete()
        db.query(KnowledgePoint).filter(KnowledgePoint.id == kp_id).delete()
        db.query(Student).filter(Student.id == student_id).delete()
        db.commit()
        db.close()


def test_ending_session_is_idempotent_and_writes_provenance():
    db = SessionLocal()
    token = uuid.uuid4().hex[:8]
    student = _student(db, token)
    tutor_session = TutorSession(student_id=student.id, subject="数学")
    db.add(tutor_session)
    db.flush()
    db.add_all(
        [
            Message(session_id=tutor_session.id, role="user", content="我总把移项符号写错。"),
            Message(session_id=tutor_session.id, role="assistant", content="先圈出要移动的项。"),
        ]
    )
    db.commit()
    db.refresh(tutor_session)
    student_id, session_id = student.id, tutor_session.id
    collection = RecordingCollection()
    try:
        first = end_session_with_summary(db, tutor_session, collection=collection)
        second = end_session_with_summary(db, tutor_session, collection=collection)
        assert first["already_ended"] is False
        assert second["already_ended"] is True
        assert second["memory_id"] == first["memory_id"]
        memories = (
            db.query(Memory)
            .filter(Memory.source_session_id == session_id)
            .all()
        )
        assert len(memories) == 1
        provenance = memories[0].structured_data["provenance"]
        assert provenance["source_session_id"] == session_id
        assert provenance["source_message_id"] is not None
        assert provenance["model_name"] == "deterministic-extractive"
        assert len(collection.upserts) == 1
    finally:
        db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id).delete()
        db.query(Memory).filter(Memory.student_id == student_id).delete()
        db.query(Message).filter(Message.session_id == session_id).delete()
        db.query(TutorSession).filter(TutorSession.id == session_id).delete()
        db.query(Student).filter(Student.id == student_id).delete()
        db.commit()
        db.close()


def test_memory_from_first_session_is_available_in_second_session(monkeypatch):
    db = SessionLocal()
    token = uuid.uuid4().hex[:8]
    student = _student(db, token)
    first_session = TutorSession(student_id=student.id, subject="数学")
    second_session = TutorSession(student_id=student.id, subject="数学")
    db.add_all([first_session, second_session])
    db.flush()
    source_message = Message(
        session_id=first_session.id,
        role="assistant",
        content="记录学生偏好。",
    )
    db.add(source_message)
    db.commit()
    db.refresh(source_message)
    student_id = student.id
    first_session_id = first_session.id
    session_ids = [first_session.id, second_session.id]
    message_id = source_message.id
    db.close()

    storage = MemoryStorage()
    storage.collection = RecordingCollection()
    monkeypatch.setattr(storage, "_link_knowledge_point", lambda _db, _memory: None)
    monkeypatch.setattr(
        "app.services.memory.storage.settings_service.get_float",
        lambda _key, default: default,
    )

    class EmptyQueryCollection:
        def query(self, **_kwargs):
            return {"ids": [[]], "documents": [[]], "distances": [[]]}

    monkeypatch.setattr(
        "app.services.memory.retriever.embed_query", lambda _query: [0.0]
    )
    try:
        storage.write(
            student_id,
            session_id=first_session_id,
            source_message_id=message_id,
            model_name="test-model",
            items=[
                {
                    "type": "semantic",
                    "predicate": "学习偏好",
                    "object": "先看图再看公式",
                    "confidence": 0.9,
                }
            ],
        )
        result = MemoryRetriever(collection=EmptyQueryCollection()).retrieve(
            student_id,
            "新会话应该怎么讲",
        )
        assert "先看图再看公式" in result["profile_summary"]
        db = SessionLocal()
        memory = db.query(Memory).filter(Memory.student_id == student_id).one()
        provenance = memory.structured_data["provenance"]
        assert provenance["source_session_id"] == first_session_id
        assert provenance["source_message_id"] == message_id
        db.close()
    finally:
        db = SessionLocal()
        db.query(ReviewPlan).filter(ReviewPlan.student_id == student_id).delete()
        db.query(Memory).filter(Memory.student_id == student_id).delete()
        db.query(StudentProfile).filter(StudentProfile.student_id == student_id).delete()
        db.query(Message).filter(Message.session_id.in_(session_ids)).delete(
            synchronize_session=False
        )
        db.query(TutorSession).filter(TutorSession.id.in_(session_ids)).delete(
            synchronize_session=False
        )
        db.query(Student).filter(Student.id == student_id).delete()
        db.commit()
        db.close()
