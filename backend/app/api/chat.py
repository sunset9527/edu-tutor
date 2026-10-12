"""对话相关路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.chat_graph import run_chat
from app.api.access import get_owned_session, get_owned_student
from app.api.auth import require_current_user_id
from app.core.config import settings
from app.core.database import get_db
from app.models.session import Session as TutorSession
from app.models.student import Student
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


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

    # 无 session_id 时自动创建新会话
    session_id = payload.session_id
    if session_id is None:
        tutor_session = TutorSession(student_id=student.id, subject=student.subject)
        db.add(tutor_session)
        db.commit()
        db.refresh(tutor_session)
        session_id = tutor_session.id
    else:
        exists = get_owned_session(db, session_id, user_id)
        if exists.student_id != student.id:
            raise HTTPException(status_code=404, detail="会话不存在")

    response = run_chat(student_id=student.id, session_id=session_id, user_message=payload.message)
    return ChatResponse(session_id=session_id, response=response)
