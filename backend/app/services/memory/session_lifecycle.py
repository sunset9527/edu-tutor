"""辅导会话结束、摘要与情景记忆落库。"""

from datetime import datetime

from app.models.memory import Memory
from app.models.session import Message, Session as TutorSession
from app.services.memory.chroma_client import get_memory_collection
from app.services.memory.forgetting import ReviewScheduler
from app.services.memory.lifecycle import build_provenance, build_session_summary
from app.services.memory.storage import delete_memory_vector, upsert_memory_vector


def end_session_with_summary(
    db,
    tutor_session: TutorSession,
    *,
    collection=None,
    now: datetime | None = None,
) -> dict:
    """幂等结束会话，并在同一事务中写摘要和 episodic 记忆。"""
    if tutor_session.ended_at is not None:
        existing = (
            db.query(Memory)
            .filter(
                Memory.source_session_id == tutor_session.id,
                Memory.memory_type == "episodic",
            )
            .all()
        )
        summary_memory = next(
            (
                row
                for row in existing
                if (row.structured_data or {}).get("source_kind") == "session_summary"
            ),
            None,
        )
        return {
            "session_id": tutor_session.id,
            "summary": tutor_session.summary or "",
            "memory_id": summary_memory.id if summary_memory else None,
            "already_ended": True,
        }

    rows = (
        db.query(Message)
        .filter(Message.session_id == tutor_session.id)
        .order_by(Message.id)
        .all()
    )
    summary = build_session_summary([(row.role, row.content) for row in rows])
    if not summary:
        summary = "本次会话没有可摘要的消息"
    now = now or datetime.now()
    provenance = build_provenance(
        session_id=tutor_session.id,
        message_id=rows[-1].id if rows else None,
        extraction_version="v1.5-session-summary",
        model_name="deterministic-extractive",
        extracted_at=now,
    )
    memory = Memory(
        student_id=tutor_session.student_id,
        memory_type="episodic",
        content=f"学习会话摘要：{summary}",
        structured_data={
            "predicate": "学习事件",
            "object": summary,
            "source_kind": "session_summary",
            "provenance": provenance,
        },
        source_session_id=tutor_session.id,
        confidence=1.0,
        status="active",
    )
    db.add(memory)
    db.flush()
    collection = collection or get_memory_collection()
    vector_written = False
    try:
        upsert_memory_vector(memory, collection=collection)
        vector_written = True
        ReviewScheduler().create_plan(db, tutor_session.student_id, "memory", memory.id)
        tutor_session.summary = summary
        tutor_session.ended_at = now
        db.commit()
    except Exception:
        db.rollback()
        if vector_written:
            delete_memory_vector(memory.id, collection=collection)
        raise
    return {
        "session_id": tutor_session.id,
        "summary": summary,
        "memory_id": memory.id,
        "already_ended": False,
    }
