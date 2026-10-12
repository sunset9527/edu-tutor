"""生成 v1.5 验收 JSON 的可复现脚本；使用临时 MySQL 记录并在结束时清理。"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint, KnowledgePointLink, WrongQuestion
from app.models.memory import Memory, ReviewPlan
from app.models.session import Message, Session as TutorSession
from app.models.student import Student, StudentProfile
from app.services.knowledge.path_service import build_personalized_learning_path
from app.services.memory import retriever as retriever_module
from app.services.memory.learning_state import record_practice_result
from app.services.memory.retriever import MemoryRetriever
from app.services.memory.storage import MemoryStorage


class EvidenceCollection:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def upsert(self, *, ids, documents, metadatas, embeddings):
        for index, memory_id in enumerate(ids):
            self.rows[memory_id] = {
                "document": documents[index],
                "metadata": metadatas[index],
                "embedding": embeddings[index],
            }

    def delete(self, *, ids):
        for memory_id in ids:
            self.rows.pop(memory_id, None)


class RankedQueryCollection(EvidenceCollection):
    def __init__(self, memories):
        super().__init__()
        self.memories = memories

    def query(self, **_kwargs):
        return {
            "ids": [[str(memory.id) for memory in self.memories]],
            "documents": [[memory.content for memory in self.memories]],
            "distances": [[0.08, 0.35]],
        }


def main() -> None:
    token = uuid.uuid4().hex[:10]
    db = SessionLocal()
    original_embed_query = retriever_module.embed_query
    original_get_int = retriever_module.settings_service.get_int
    student_ids: list[int] = []
    session_ids: list[int] = []
    kp_ids: list[int] = []
    try:
        prereqs = [
            KnowledgePoint(
                subject="数学",
                grade="初一",
                title="整数运算",
                slug=f"v15-evidence-integer-{token}",
                difficulty="基础",
            ),
            KnowledgePoint(
                subject="数学",
                grade="初一",
                title="等式性质",
                slug=f"v15-evidence-equality-{token}",
                difficulty="基础",
            ),
        ]
        target = KnowledgePoint(
            subject="数学",
            grade="初一",
            title="一元一次方程",
            slug=f"v15-evidence-equation-{token}",
            difficulty="进阶",
        )
        db.add_all([*prereqs, target])
        db.flush()
        kp_ids = [kp.id for kp in prereqs] + [target.id]
        db.add_all(
            [
                KnowledgePointLink(
                    source_kp_id=kp.id,
                    target_kp_id=target.id,
                    link_type="prerequisite",
                )
                for kp in prereqs
            ]
        )
        students = [
            Student(name="验收学生甲", grade="初一", subject="数学"),
            Student(name="验收学生乙", grade="初一", subject="数学"),
            Student(name="验收学生丙", grade="初一", subject="数学"),
        ]
        db.add_all(students)
        db.flush()
        student_ids = [student.id for student in students]
        db.commit()

        profiles = [
            ("整数运算符号", "先看图再看公式"),
            ("等式性质", "先做例题再总结"),
            ("移项变号", "分步骤口述思路"),
        ]
        sessions_by_student: dict[int, list[int]] = {}
        fake_vectors = EvidenceCollection()
        for student, (weakness, preference) in zip(students, profiles):
            created_sessions = [
                TutorSession(student_id=student.id, subject="数学") for _ in range(3)
            ]
            db.add_all(created_sessions)
            db.flush()
            ids = [row.id for row in created_sessions]
            sessions_by_student[student.id] = ids
            session_ids.extend(ids)
            db.add_all(
                [
                    Message(
                        session_id=ids[0],
                        role="user",
                        content=f"我的薄弱点是{weakness}，我喜欢{preference}。",
                    ),
                    Message(
                        session_id=ids[1],
                        role="user",
                        content="请按你记住的方式继续讲。",
                    ),
                    Message(
                        session_id=ids[2],
                        role="user",
                        content="我完成了本轮练习。",
                    ),
                ]
            )
        db.commit()

        storage = MemoryStorage()
        storage.collection = fake_vectors
        storage._link_knowledge_point = lambda _db, _memory: None
        for student, (weakness, preference) in zip(students, profiles):
            first_session_id = sessions_by_student[student.id][0]
            message = (
                db.query(Message)
                .filter(Message.session_id == first_session_id)
                .one()
            )
            storage.write(
                student.id,
                session_id=first_session_id,
                source_message_id=message.id,
                model_name="v1.5-evidence-fixture",
                items=[
                    {
                        "type": "semantic",
                        "predicate": "薄弱点",
                        "object": weakness,
                        "confidence": 0.9,
                    },
                    {
                        "type": "semantic",
                        "predicate": "学习偏好",
                        "object": preference,
                        "confidence": 0.9,
                    },
                ],
            )

        class EmptyQueryCollection:
            def query(self, **_kwargs):
                return {"ids": [[]], "documents": [[]], "distances": [[]]}

        retriever_module.embed_query = lambda _query: [0.0]
        retrieved_profiles = {
            student.id: MemoryRetriever(collection=EmptyQueryCollection()).retrieve(
                student.id, "请延续上次的个性化讲解"
            )["profile_summary"]
            for student in students
        }

        mastery_events = {
            students[0].id: [(prereqs[0].id, True), (prereqs[0].id, True)],
            students[1].id: [(prereqs[1].id, True), (prereqs[1].id, True)],
            students[2].id: [(prereqs[0].id, False), (prereqs[1].id, False)],
        }
        event_results: dict[int, list[dict]] = {}
        for student in students:
            event_results[student.id] = [
                record_practice_result(
                    student.id,
                    kp_id,
                    success=success,
                    collection=fake_vectors,
                )
                for kp_id, success in mastery_events[student.id]
            ]

        # 外部服务使用独立会话提交；结束当前 REPEATABLE READ 快照后再读取新事实。
        db.rollback()

        comparisons = []
        for student, (weakness, preference) in zip(students, profiles):
            result = build_personalized_learning_path(db, student.id, target.id)
            pending_count = (
                db.query(ReviewPlan)
                .filter(
                    ReviewPlan.student_id == student.id,
                    ReviewPlan.target_type == "knowledge_point",
                    ReviewPlan.status == "pending",
                )
                .count()
            )
            comparisons.append(
                {
                    "student": student.name,
                    "student_id": student.id,
                    "session_ids": sessions_by_student[student.id],
                    "session_1_profile": {
                        "weakness": weakness,
                        "preference": preference,
                    },
                    "session_2_retrieved_profile": retrieved_profiles[student.id],
                    "session_3_mastery_events": event_results[student.id],
                    "pending_knowledge_reviews": pending_count,
                    "path": result,
                }
            )

        trace_memories = (
            db.query(Memory)
            .filter(Memory.student_id == students[0].id)
            .order_by(Memory.id)
            .limit(2)
            .all()
        )
        retriever_module.settings_service.get_int = (
            lambda key, default: 0
            if key in {"retrieval_profile_quota", "retrieval_recent_quota"}
            else (1 if key == "retrieval_relevant_quota" else default)
        )
        fixed_now = datetime(2026, 10, 12, 12, 0, 0)
        trace_result = MemoryRetriever(
            collection=RankedQueryCollection(trace_memories),
            now_factory=lambda: fixed_now,
        ).retrieve(students[0].id, "我该怎样学习方程？")
        retriever_module.settings_service.get_int = original_get_int
        retriever_module.embed_query = original_embed_query

        evidence = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "dataset": "临时数据库验收夹具；脚本结束后清理",
            "retrieval_trace": trace_result["trace"],
            "selected_memories": trace_result["relevant_memories"],
            "three_student_comparison": comparisons,
        }
        print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
    finally:
        retriever_module.embed_query = original_embed_query
        retriever_module.settings_service.get_int = original_get_int
        if student_ids:
            db.query(ReviewPlan).filter(ReviewPlan.student_id.in_(student_ids)).delete(
                synchronize_session=False
            )
            db.query(Memory).filter(Memory.student_id.in_(student_ids)).delete(
                synchronize_session=False
            )
            db.query(StudentProfile).filter(
                StudentProfile.student_id.in_(student_ids)
            ).delete(synchronize_session=False)
            db.query(WrongQuestion).filter(
                WrongQuestion.student_id.in_(student_ids)
            ).delete(synchronize_session=False)
            db.query(Message).filter(Message.session_id.in_(session_ids)).delete(
                synchronize_session=False
            )
            db.query(TutorSession).filter(TutorSession.id.in_(session_ids)).delete(
                synchronize_session=False
            )
        if kp_ids:
            db.query(KnowledgePointLink).filter(
                KnowledgePointLink.target_kp_id.in_(kp_ids)
            ).delete(synchronize_session=False)
            db.query(KnowledgePointLink).filter(
                KnowledgePointLink.source_kp_id.in_(kp_ids)
            ).delete(synchronize_session=False)
        if student_ids:
            db.query(Student).filter(Student.id.in_(student_ids)).delete(
                synchronize_session=False
            )
        if kp_ids:
            db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(kp_ids)).delete(
                synchronize_session=False
            )
        db.commit()
        db.close()


if __name__ == "__main__":
    main()
