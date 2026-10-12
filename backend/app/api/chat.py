"""对话相关路由"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.chat_graph import run_chat
from app.api.access import get_owned_session, get_owned_student
from app.api.auth import require_current_user_id
from app.core.config import settings
from app.core.database import get_db
from app.models.session import Session as TutorSession
from app.models.session import Message
from app.models.student import Student
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.memory.session_lifecycle import end_session_with_summary
from app.services.chat_stream import encode_sse, stream_chat_events

router = APIRouter(prefix="/api", tags=["chat"])


def _resolve_session(db: Session, student: Student, session_id: int | None, user_id: int) -> int:
    if session_id is None:
        tutor_session = TutorSession(student_id=student.id, subject=student.subject)
        db.add(tutor_session)
        db.commit()
        db.refresh(tutor_session)
        return tutor_session.id
    exists = get_owned_session(db, session_id, user_id)
    if exists.student_id != student.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return exists.id


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    student = get_owned_student(db, payload.student_id, user_id)

    # LLM 未配置时快速失败（避免卡 60 秒超时）
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY 未配置，请在 backend/.env 中设置后重启",
        )

    session_id = _resolve_session(db, student, payload.session_id, user_id)

    response = run_chat(student_id=student.id, session_id=session_id, user_message=payload.message)
    return ChatResponse(session_id=session_id, response=response)


@router.post("/chat/stream")
def chat_stream(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """流式对话：用命名 SSE 事件公开检索、生成、记忆与画像更新过程。"""
    student = get_owned_student(db, payload.student_id, user_id)
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY 未配置，请在 backend/.env 中设置后重启",
        )
    session_id = _resolve_session(db, student, payload.session_id, user_id)

    def frames():
        for item in stream_chat_events(
            student_id=student.id,
            session_id=session_id,
            user_message=payload.message,
        ):
            yield encode_sse(item["event"], item["data"])

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Session-Id": str(session_id),
        },
    )


@router.get("/sessions/{session_id}/messages")
def session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """按数据库顺序恢复一个归属当前账号的会话。"""
    tutor_session = get_owned_session(db, session_id, user_id)
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.id)
        .all()
    )
    return {
        "session_id": session_id,
        "student_id": tutor_session.student_id,
        "subject": tutor_session.subject,
        "messages": [
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.post("/sessions/{session_id}/end")
def end_session(
    session_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """结束会话并生成可追溯的情景记忆。"""
    tutor_session = get_owned_session(db, session_id, user_id)
    return end_session_with_summary(db, tutor_session)
