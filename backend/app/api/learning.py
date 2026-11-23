"""v1.8 学习目标与诊断 API。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.access import get_owned_student
from app.api.auth import require_current_user_id
from app.core.database import get_db
from app.models.learning import LearningGoal
from app.models.diagnostics import DiagnosticAnswer, DiagnosticQuestion, DiagnosticSession
from app.services.diagnostics import save_answer, start_or_resume_diagnostic, submit_diagnostic
from app.services.learning_plans import generate_learning_plan
from app.services.learning_goals import append_learning_goal_version, create_learning_goal


router = APIRouter(prefix="/api/learning", tags=["learning"])


class LearningGoalCreate(BaseModel):
    student_id: int
    target_date: date
    weekly_minutes: int = Field(gt=0, le=10_080)
    subject: str = Field(min_length=1, max_length=20)
    target_level: str = Field(min_length=1, max_length=20)
    target_knowledge_point_ids: list[int] = Field(min_length=1)


class LearningGoalVersionUpdate(BaseModel):
    target_date: date | None = None
    weekly_minutes: int | None = Field(default=None, gt=0, le=10_080)
    status: str | None = Field(default=None, pattern="^(active|paused|ended)$")
    change_reason: str = Field(min_length=1, max_length=50)


class DiagnosticStart(BaseModel):
    student_id: int
    goal_id: int


class DiagnosticAnswerSave(BaseModel):
    raw_answer: dict
    elapsed_seconds: int | None = Field(default=None, ge=0)
    confidence: int | None = Field(default=None, ge=1, le=5)


class LearningPlanCreate(BaseModel):
    student_id: int
    goal_id: int
    adjustment_reason: str = Field(default="initial", min_length=1, max_length=50)


def _goal_payload(goal: LearningGoal) -> dict:
    version = goal.current_version
    assert version is not None
    return {
        "id": goal.id,
        "student_id": goal.student_id,
        "current_version": {
            "id": version.id,
            "version_no": version.version_no,
            "knowledge_version_id": version.knowledge_version_id,
            "target_date": version.target_date.isoformat(),
            "weekly_minutes": version.weekly_minutes,
            "subject": version.subject,
            "target_level": version.target_level,
            "status": version.status,
            "change_reason": version.change_reason,
            "target_knowledge_point_ids": [target.knowledge_point_id for target in version.targets],
        },
    }


def _session_payload(db: Session, session: DiagnosticSession) -> dict:
    answers = db.query(DiagnosticAnswer).filter(DiagnosticAnswer.session_id == session.id).order_by(DiagnosticAnswer.id).all()
    return {"id": session.id, "status": session.status, "goal_version_id": session.goal_version_id, "knowledge_version_id": session.knowledge_version_id, "questions": [{"question_id": answer.question_id, "stem": db.get(DiagnosticQuestion, answer.question_id).stem, "question_type": db.get(DiagnosticQuestion, answer.question_id).question_type, "options": db.get(DiagnosticQuestion, answer.question_id).options_json, "raw_answer": answer.raw_answer, "final_score": answer.final_score, "confirmed": answer.confirmed_at is not None} for answer in answers]}


@router.post("/plans", status_code=201)
def create_learning_plan(payload: LearningPlanCreate, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    get_owned_student(db, payload.student_id, user_id)
    try:
        plan = generate_learning_plan(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from app.models.learning import LearningPlanItem
    items = db.query(LearningPlanItem).filter(LearningPlanItem.plan_version_id == plan.id).order_by(LearningPlanItem.sequence_no).all()
    return {"id": plan.id, "status": plan.status, "scheduled_minutes": plan.scheduled_minutes, "missing_minutes": plan.missing_minutes, "items": [{"knowledge_point_id": item.knowledge_point_id, "week_no": item.week_no, "estimated_minutes": item.estimated_minutes, "reasons": item.recommendation_reasons, "scheduled": item.scheduled} for item in items]}


@router.post("/diagnostics", status_code=201)
def start_diagnostic(payload: DiagnosticStart, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    get_owned_student(db, payload.student_id, user_id)
    try:
        return _session_payload(db, start_or_resume_diagnostic(db, student_id=payload.student_id, goal_id=payload.goal_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/diagnostics/{session_id}/answers/{question_id}")
def save_diagnostic_answer(session_id: int, question_id: int, payload: DiagnosticAnswerSave, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    session = db.get(DiagnosticSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="诊断不存在")
    get_owned_student(db, session.student_id, user_id)
    try:
        answer = save_answer(db, session=session, question_id=question_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": answer.id, "question_id": answer.question_id, "final_score": answer.final_score, "confirmed": answer.confirmed_at is not None}


@router.post("/diagnostics/{session_id}/submit")
def submit_diagnostic_session(session_id: int, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    session = db.get(DiagnosticSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="诊断不存在")
    get_owned_student(db, session.student_id, user_id)
    try:
        results = submit_diagnostic(db, session=session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session_id": session.id, "status": "submitted", "results": [{"knowledge_point_id": row.knowledge_point_id, "mastery": row.mastery, "evidence_status": row.evidence_status, "score_rate": row.score_rate} for row in results]}


@router.post("/goals", status_code=201)
def create_goal(
    payload: LearningGoalCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """创建目标，并固定当前 active 的知识版本。"""
    get_owned_student(db, payload.student_id, user_id)
    try:
        goal = create_learning_goal(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _goal_payload(goal)


@router.patch("/goals/{goal_id}")
def update_goal(
    goal_id: int,
    payload: LearningGoalVersionUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """追加目标版本；用于修改、暂停、恢复或结束。"""
    goal = db.get(LearningGoal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="学习目标不存在")
    get_owned_student(db, goal.student_id, user_id)
    try:
        updated = append_learning_goal_version(db, goal_id=goal_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _goal_payload(updated)


@router.get("/goals/{student_id}")
def current_learning_goal(
    student_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """返回当前账号学生的最新学习目标及其当前版本。"""
    get_owned_student(db, student_id, user_id)
    goal = (
        db.query(LearningGoal)
        .filter(LearningGoal.student_id == student_id)
        .order_by(LearningGoal.id.desc())
        .first()
    )
    if goal is None or goal.current_version is None:
        raise HTTPException(status_code=404, detail="尚未设置学习目标")
    return _goal_payload(goal)
