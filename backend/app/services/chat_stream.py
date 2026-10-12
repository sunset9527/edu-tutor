"""v1.6 对话 SSE 编排与事件契约。"""

import json
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.chat_graph import SYSTEM_PROMPT, _load_recent_messages
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.llm import create_llm
from app.models.memory import Memory
from app.models.session import Message
from app.models.student import StudentProfile
from app.services.memory.extractor import MemoryExtractor
from app.services.memory.retriever import MemoryRetriever
from app.services.memory.storage import MemoryStorage


def encode_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunk_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", "")) if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "")


def save_turn_messages(session_id: int, user_message: str, ai_response: str) -> list[int]:
    db = SessionLocal()
    try:
        rows = [
            Message(session_id=session_id, role="user", content=user_message),
            Message(session_id=session_id, role="assistant", content=ai_response),
        ]
        db.add_all(rows)
        db.flush()
        ids = [row.id for row in rows]
        db.commit()
        return ids
    finally:
        db.close()


def _memory_snapshot(student_id: int) -> dict[int, tuple]:
    db = SessionLocal()
    try:
        rows = db.query(Memory).filter(Memory.student_id == student_id).all()
        return {
            row.id: (
                row.content,
                row.status,
                row.mastery,
                json.dumps(row.structured_data or {}, ensure_ascii=False, sort_keys=True),
            )
            for row in rows
        }
    finally:
        db.close()


def _serialize_memory(memory: Memory) -> dict:
    return {
        "id": memory.id,
        "memory_type": memory.memory_type,
        "content": memory.content,
        "confidence": memory.confidence,
        "mastery": memory.mastery,
        "status": memory.status,
    }


def process_turn_memory(
    *,
    student_id: int,
    session_id: int,
    user_message: str,
    ai_response: str,
    profile_summary: str,
    source_message_id: int | None,
) -> dict:
    """提取并存储本轮记忆，返回前端可解释差异。"""
    before = _memory_snapshot(student_id)
    try:
        candidates = MemoryExtractor().extract(
            user_message=user_message,
            ai_response=ai_response,
            profile_summary=profile_summary,
        )
        written_count = MemoryStorage().write(
            student_id=student_id,
            session_id=session_id,
            items=candidates,
            source_message_id=source_message_id,
            extraction_version="v1.6-stream",
            model_name=settings.deepseek_model,
        )
        after = _memory_snapshot(student_id)
        db = SessionLocal()
        try:
            rows = {
                row.id: row
                for row in db.query(Memory)
                .filter(Memory.student_id == student_id)
                .all()
            }
            new_ids = [memory_id for memory_id in after if memory_id not in before]
            updated_ids = [
                memory_id
                for memory_id in after
                if memory_id in before and after[memory_id] != before[memory_id]
            ]
            new_memories = [_serialize_memory(rows[memory_id]) for memory_id in new_ids]
            updated_memories = [
                _serialize_memory(rows[memory_id]) for memory_id in updated_ids
            ]
        finally:
            db.close()
        suggestions = [
            {
                "type": "wrong_question",
                "question_text": item.get("object", ""),
                "knowledge_point_id": item.get("knowledge_point_id"),
            }
            for item in candidates
            if item.get("predicate") == "错题" and item.get("object")
        ]
        suggestions.extend(
            {
                "type": "review",
                "memory_id": memory["id"],
                "content": memory["content"],
            }
            for memory in new_memories
            if memory.get("status") == "active"
        )
        return {
            "candidates": candidates,
            "written_count": written_count,
            "new_memories": new_memories,
            "updated_memories": updated_memories,
            "suggestions": suggestions,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "candidates": [],
            "written_count": 0,
            "new_memories": [],
            "updated_memories": [],
            "suggestions": [],
            "error": str(exc),
        }


def load_profile_snapshot(student_id: int) -> dict:
    db = SessionLocal()
    try:
        profile = db.get(StudentProfile, student_id)
        return {
            "weaknesses": (profile.weaknesses if profile else []) or [],
            "strengths": (profile.strengths if profile else []) or [],
        }
    finally:
        db.close()


def stream_chat_events(
    *,
    student_id: int,
    session_id: int,
    user_message: str,
    retriever=None,
    llm=None,
    history_loader=None,
    message_saver=None,
    memory_processor=None,
    profile_loader=None,
):
    """产生结构化事件；API 层仅负责编码为 SSE。"""
    sequence = 0

    def event(name: str, payload: dict | None = None) -> dict:
        nonlocal sequence
        sequence += 1
        return {
            "event": name,
            "data": {
                "sequence": sequence,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                **(payload or {}),
            },
        }

    yield event("generation_started")
    try:
        retriever = retriever or MemoryRetriever()
        result = retriever.retrieve(student_id, user_message)
        selected = [
            row
            for row in result.get("trace", {}).get("candidates", [])
            if row.get("selected")
        ]
        yield event(
            "memory_retrieved",
            {
                "profile_summary": result.get("profile_summary", ""),
                "relevant_memories": result.get("relevant_memories", []),
                "recent_events": result.get("recent_events", []),
                "selected": selected,
                "trace": result.get("trace", {}),
            },
        )

        history_loader = history_loader or _load_recent_messages
        history = history_loader(session_id)
        system = SYSTEM_PROMPT
        injection = retriever.build_injection_text(result)
        if injection:
            system += "\n\n以下是这个学生的长期记忆，请充分利用它提供个性化辅导：\n" + injection
        messages = [SystemMessage(content=system), *history, HumanMessage(content=user_message)]
        llm = llm or create_llm(streaming=True)
        chunks: list[str] = []
        for chunk in llm.stream(messages):
            text = _chunk_text(chunk.content)
            if text:
                chunks.append(text)
                yield event("response_chunk", {"text": text})
        response = "".join(chunks)

        message_saver = message_saver or save_turn_messages
        message_ids = message_saver(session_id, user_message, response)
        yield event("messages_saved", {"message_ids": message_ids})

        memory_processor = memory_processor or process_turn_memory
        memory_result = memory_processor(
            student_id=student_id,
            session_id=session_id,
            user_message=user_message,
            ai_response=response,
            profile_summary=result.get("profile_summary", ""),
            source_message_id=message_ids[-1] if message_ids else None,
        )
        yield event("memory_extracted", memory_result)

        profile_loader = profile_loader or load_profile_snapshot
        yield event("profile_updated", profile_loader(student_id))
        yield event(
            "completed",
            {"response": response, "message_ids": message_ids},
        )
    except Exception as exc:  # noqa: BLE001
        yield event("failed", {"error": str(exc)})
