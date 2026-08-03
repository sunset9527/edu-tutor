"""对话相关路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.chat_graph import run_chat
from app.core.config import settings
from app.core.database import get_db
from app.models.session import Session as TutorSession
from app.models.student import Student
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    # LLM 未配置时快速失败（避免卡 60 秒超时）
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY 未配置，请在 backend/.env 中设置后重启",
        )

    student = db.get(Student, payload.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")

    # 无 session_id 时自动创建新会话
    session_id = payload.session_id
    if session_id is None:
        tutor_session = TutorSession(student_id=student.id, subject=student.subject)
        db.add(tutor_session)
        db.commit()
        db.refresh(tutor_session)
        session_id = tutor_session.id
    else:
        exists = db.get(TutorSession, session_id)
        if not exists:
            raise HTTPException(status_code=404, detail="会话不存在")

    response = run_chat(student_id=student.id, session_id=session_id, user_message=payload.message)
    return ChatResponse(session_id=session_id, response=response)
