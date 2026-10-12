"""练习结果驱动的掌握状态与知识点复习计划。"""

from datetime import datetime, timedelta
from typing import Callable

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgePoint
from app.models.memory import Memory, ReviewPlan
from app.services import settings_service
from app.services.memory.chroma_client import get_memory_collection
from app.services.memory.lifecycle import transition_mastery
from app.services.memory.storage import delete_memory_vector, upsert_memory_vector


def _find_mastery_memory(db, student_id: int, knowledge_point_id: int) -> Memory | None:
    rows = (
        db.query(Memory)
        .filter(
            Memory.student_id == student_id,
            Memory.knowledge_point_id == knowledge_point_id,
            Memory.memory_type == "semantic",
            Memory.status == "active",
        )
        .all()
    )
    return next(
        (row for row in rows if (row.structured_data or {}).get("predicate") == "掌握状态"),
        None,
    )


def record_practice_result(
    student_id: int,
    knowledge_point_id: int,
    *,
    success: bool,
    now: datetime | None = None,
    collection=None,
    transaction_mutation: Callable | None = None,
) -> dict:
    """以一次练习事实原子更新业务记录、掌握记忆、向量和复习计划。"""
    now = now or datetime.now()
    collection = collection or get_memory_collection()
    db = SessionLocal()
    vector_memory_id: int | None = None
    old_snapshot: dict | None = None
    try:
        kp = db.get(KnowledgePoint, knowledge_point_id)
        if not kp:
            raise ValueError("知识点不存在")
        transaction_result = transaction_mutation(db) if transaction_mutation else None
        memory = _find_mastery_memory(db, student_id, knowledge_point_id)
        old_mastery = memory.mastery if memory else "不懂"
        new_mastery = transition_mastery(old_mastery, success)
        structured = {
            "predicate": "掌握状态",
            "object": kp.title,
            "knowledge_point_id": knowledge_point_id,
            "last_practice_result": "correct" if success else "wrong",
            "last_practice_at": now.isoformat(timespec="seconds"),
        }
        if memory is None:
            memory = Memory(
                student_id=student_id,
                memory_type="semantic",
                content=f"掌握状态：{kp.title}（{new_mastery}）",
                structured_data=structured,
                knowledge_point_id=knowledge_point_id,
                confidence=1.0,
                mastery=new_mastery,
                last_reviewed_at=now,
                status="active",
            )
            db.add(memory)
            db.flush()
        else:
            old_snapshot = {
                "id": memory.id,
                "student_id": memory.student_id,
                "memory_type": memory.memory_type,
                "content": memory.content,
                "structured_data": dict(memory.structured_data or {}),
            }
            memory.content = f"掌握状态：{kp.title}（{new_mastery}）"
            memory.structured_data = structured
            memory.mastery = new_mastery
            memory.last_reviewed_at = now

        upsert_memory_vector(memory, collection=collection)
        vector_memory_id = memory.id

        base_interval = settings_service.get_int("review_interval_base", 1)
        pending = (
            db.query(ReviewPlan)
            .filter(
                ReviewPlan.student_id == student_id,
                ReviewPlan.target_type == "knowledge_point",
                ReviewPlan.target_id == knowledge_point_id,
                ReviewPlan.status == "pending",
            )
            .order_by(ReviewPlan.id.desc())
            .first()
        )
        if success:
            next_interval = max(base_interval, (pending.interval_days * 2) if pending else base_interval * 2)
            if pending:
                pending.status = "done"
            db.add(
                ReviewPlan(
                    student_id=student_id,
                    target_type="knowledge_point",
                    target_id=knowledge_point_id,
                    interval_days=next_interval,
                    next_review_at=now + timedelta(days=next_interval),
                    status="pending",
                )
            )
        elif pending:
            pending.interval_days = base_interval
            pending.next_review_at = now + timedelta(days=base_interval)
        else:
            db.add(
                ReviewPlan(
                    student_id=student_id,
                    target_type="knowledge_point",
                    target_id=knowledge_point_id,
                    interval_days=base_interval,
                    next_review_at=now + timedelta(days=base_interval),
                    status="pending",
                )
            )
        db.commit()
        result = {
            "knowledge_point_id": knowledge_point_id,
            "memory_id": memory.id,
            "previous_mastery": old_mastery,
            "mastery": new_mastery,
            "success": success,
        }
        if transaction_mutation is not None:
            result["transaction_result"] = transaction_result
        return result
    except Exception:
        db.rollback()
        if vector_memory_id is not None:
            if old_snapshot is None:
                delete_memory_vector(vector_memory_id, collection=collection)
            else:
                restored = Memory(**old_snapshot)
                upsert_memory_vector(restored, collection=collection)
        raise
    finally:
        db.close()
