"""v1.5 可解释检索追踪集成测试。"""

import uuid
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.models.memory import Memory
from app.models.student import Student
from app.services.memory import retriever as retriever_module
from app.services.memory.retriever import MemoryRetriever


class QueryCollection:
    def __init__(self, memories):
        self.memories = memories

    def query(self, **_kwargs):
        return {
            "ids": [[str(row.id) for row in self.memories]],
            "documents": [[row.content for row in self.memories]],
            "distances": [[0.1, 0.2]],
        }


def test_trace_contains_scores_rank_rejection_and_updates_access(monkeypatch):
    db = SessionLocal()
    token = uuid.uuid4().hex[:8]
    student = Student(name=f"检索-{token}", grade="初一", subject="数学")
    db.add(student)
    db.flush()
    old_time = datetime.now() - timedelta(days=5)
    memories = [
        Memory(
            student_id=student.id,
            memory_type="procedural",
            content="有效策略：画图",
            structured_data={"predicate": "有效策略", "object": "画图"},
            confidence=0.9,
            strength=0.8,
            status="active",
            created_at=old_time,
        ),
        Memory(
            student_id=student.id,
            memory_type="procedural",
            content="有效策略：举例",
            structured_data={"predicate": "有效策略", "object": "举例"},
            confidence=0.7,
            strength=0.6,
            status="active",
            created_at=old_time,
        ),
    ]
    db.add_all(memories)
    db.commit()
    for row in memories:
        db.refresh(row)
    student_id = student.id
    memory_ids = [row.id for row in memories]
    detached = list(memories)
    db.close()

    try:
        monkeypatch.setattr(retriever_module, "embed_query", lambda _query: [0.0])
        monkeypatch.setattr(
            retriever_module.settings_service,
            "get_int",
            lambda key, default: 1 if key == "retrieval_relevant_quota" else default,
        )
        monkeypatch.setattr(
            retriever_module.settings_service,
            "get_float",
            lambda _key, default: default,
        )
        fixed_now = datetime(2026, 10, 12, 12, 0, 0)
        result = MemoryRetriever(
            collection=QueryCollection(detached),
            now_factory=lambda: fixed_now,
        ).retrieve(student_id, "怎么讲更容易懂", top_k=3)

        assert result["relevant_memories"] == ["有效策略：画图"]
        candidates = result["trace"]["candidates"]
        assert [row["rank"] for row in candidates] == [1, 2]
        assert [row["reason"] for row in candidates] == ["selected", "quota_exceeded"]
        assert set(candidates[0]["components"]) == {
            "similarity",
            "recency",
            "retention",
            "confidence",
        }
        assert sum(result["trace"]["applied_weights"].values()) == 1.0

        db = SessionLocal()
        assert db.get(Memory, memory_ids[0]).last_accessed_at == fixed_now
        assert db.get(Memory, memory_ids[1]).last_accessed_at is None
        db.close()
    finally:
        db = SessionLocal()
        db.query(Memory).filter(Memory.id.in_(memory_ids)).delete(synchronize_session=False)
        db.query(Student).filter(Student.id == student_id).delete()
        db.commit()
        db.close()
