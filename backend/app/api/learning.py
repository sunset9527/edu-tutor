"""v1.8 学习目标与诊断 API。"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.access import get_owned_student
from app.api.auth import require_current_user_id
from app.core.database import get_db
from app.models.learning import LearningGoal, LearningPlanItem, LearningPlanVersion
from app.models.diagnostics import DiagnosticAnswer, DiagnosticKnowledgeResult, DiagnosticQuestion, DiagnosticSession
from app.models.knowledge import KnowledgePoint
from app.models.knowledge_governance import KnowledgeSourceChunk
from app.services.diagnostics import diagnostic_scope_knowledge_point_ids, save_answer, start_or_resume_diagnostic, submit_diagnostic
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
    target_knowledge_point_ids: list[int] | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern="^(active|paused|ended)$")
    change_reason: str = Field(min_length=1, max_length=50)


class DiagnosticStart(BaseModel):
    student_id: int
    goal_id: int


class DiagnosticAnswerSave(BaseModel):
    raw_answer: dict
    elapsed_seconds: int | None = Field(default=None, ge=0)
    confidence: int | None = Field(default=None, ge=1, le=5)


class DiagnosticScoreConfirm(BaseModel):
    final_score: int = Field(ge=0)


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
    questions = {question.id: question for question in db.query(DiagnosticQuestion).filter(DiagnosticQuestion.id.in_([answer.question_id for answer in answers])).all()}
    scope_ids = diagnostic_scope_knowledge_point_ids(
        db,
        goal_version_id=session.goal_version_id,
        knowledge_version_id=session.knowledge_version_id,
    )
    covered_ids = {question.knowledge_point_id for question in questions.values()}
    return {"id": session.id, "status": session.status, "goal_version_id": session.goal_version_id, "knowledge_version_id": session.knowledge_version_id, "missing_question_knowledge_point_ids": [knowledge_point_id for knowledge_point_id in scope_ids if knowledge_point_id not in covered_ids], "questions": [{"question_id": answer.question_id, "stem": questions[answer.question_id].stem, "question_type": questions[answer.question_id].question_type, "options": questions[answer.question_id].options_json, "raw_answer": answer.raw_answer, "suggested_score": answer.suggested_score, "suggestion_basis": answer.suggestion_basis, "final_score": answer.final_score, "confirmed": answer.confirmed_at is not None} for answer in answers]}


def _plan_payload(db: Session, plan: LearningPlanVersion, *, stale: bool = False) -> dict:
    items = db.query(LearningPlanItem).filter(LearningPlanItem.plan_version_id == plan.id).order_by(LearningPlanItem.sequence_no).all()
    return {
        "id": plan.id,
        "status": "stale" if stale else plan.status,
        "goal_version_id": plan.goal_version_id,
        "diagnostic_session_id": plan.diagnostic_session_id,
        "adjustment_reason": plan.adjustment_reason,
        "scheduled_minutes": plan.scheduled_minutes,
        "missing_minutes": plan.missing_minutes,
        "items": [{"knowledge_point_id": item.knowledge_point_id, "week_no": item.week_no, "estimated_minutes": item.estimated_minutes, "reasons": item.recommendation_reasons, "completion_condition": item.completion_condition, "evidence": item.evidence_json, "scheduled": item.scheduled} for item in items],
    }


@router.post("/plans", status_code=201)
def create_learning_plan(payload: LearningPlanCreate, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    get_owned_student(db, payload.student_id, user_id)
    try:
        plan = generate_learning_plan(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _plan_payload(db, plan)


@router.get("/plans/{goal_id}")
def learning_plan_history(goal_id: int, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    """返回计划版本历史；目标或诊断依据落后时在查询层标记为过期。"""
    goal = db.get(LearningGoal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="学习目标不存在")
    get_owned_student(db, goal.student_id, user_id)
    plans = db.query(LearningPlanVersion).filter(LearningPlanVersion.goal_id == goal_id).order_by(LearningPlanVersion.id.desc()).all()
    latest_session = None
    if goal.current_version is not None:
        latest_session = db.query(DiagnosticSession).filter(
            DiagnosticSession.goal_version_id == goal.current_version.id,
            DiagnosticSession.status == "submitted",
        ).order_by(DiagnosticSession.submitted_at.desc(), DiagnosticSession.id.desc()).first()
    return {
        "plans": [
            _plan_payload(
                db,
                plan,
                stale=(
                    goal.current_version is None
                    or plan.goal_version_id != goal.current_version.id
                    or (latest_session is not None and plan.diagnostic_session_id != latest_session.id)
                ),
            )
            for plan in plans
        ]
    }


@router.post("/diagnostics", status_code=201)
def start_diagnostic(payload: DiagnosticStart, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    get_owned_student(db, payload.student_id, user_id)
    try:
        return _session_payload(db, start_or_resume_diagnostic(db, student_id=payload.student_id, goal_id=payload.goal_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/diagnostics/goals/{goal_id}")
def latest_diagnostic_for_goal(goal_id: int, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    """刷新页面时恢复该目标当前版本的最近诊断，而不新建会话。"""
    goal = db.get(LearningGoal, goal_id)
    if goal is None or goal.current_version is None:
        raise HTTPException(status_code=404, detail="学习目标不存在")
    get_owned_student(db, goal.student_id, user_id)
    session = db.query(DiagnosticSession).filter(
        DiagnosticSession.goal_version_id == goal.current_version.id,
    ).order_by(DiagnosticSession.id.desc()).first()
    if session is None:
        raise HTTPException(status_code=404, detail="尚无诊断会话")
    return _session_payload(db, session)


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


@router.post("/diagnostics/{session_id}/answers/{question_id}/confirm")
def confirm_subjective_score(session_id: int, question_id: int, payload: DiagnosticScoreConfirm, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    session = db.get(DiagnosticSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="诊断不存在")
    get_owned_student(db, session.student_id, user_id)
    answer = db.query(DiagnosticAnswer).filter(DiagnosticAnswer.session_id == session_id, DiagnosticAnswer.question_id == question_id).one_or_none()
    question = db.get(DiagnosticQuestion, question_id)
    if answer is None or question is None or question.question_type == "objective":
        raise HTTPException(status_code=400, detail="只能确认该诊断中的主观题")
    if payload.final_score > question.max_score:
        raise HTTPException(status_code=400, detail="确认分数超过题目满分")
    answer.final_score = payload.final_score
    answer.confirmed_at = datetime.now()
    answer.suggestion_basis = {**(answer.suggestion_basis or {}), "confirmed_by": "student"}
    db.commit()
    return {"id": answer.id, "final_score": answer.final_score, "confirmed": True}


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


@router.get("/diagnostics/{session_id}/report")
def diagnostic_report(session_id: int, db: Session = Depends(get_db), user_id: int = Depends(require_current_user_id)):
    session = db.get(DiagnosticSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="诊断不存在")
    get_owned_student(db, session.student_id, user_id)
    rows = db.query(DiagnosticKnowledgeResult).filter(DiagnosticKnowledgeResult.session_id == session_id).order_by(DiagnosticKnowledgeResult.knowledge_point_id).all()
    point_ids = [row.knowledge_point_id for row in rows]
    points = {point.id: point for point in db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()}
    chunk_ids = [point.source_chunk_id for point in points.values() if point.source_chunk_id is not None]
    chunks = {chunk.id: chunk for chunk in db.query(KnowledgeSourceChunk).filter(KnowledgeSourceChunk.id.in_(chunk_ids)).all()}
    return {"session_id": session.id, "status": session.status, "results": [{"knowledge_point_id": row.knowledge_point_id, "knowledge_point_title": points.get(row.knowledge_point_id).title if points.get(row.knowledge_point_id) else None, "source_page_range": ([chunks[points[row.knowledge_point_id].source_chunk_id].start_page, chunks[points[row.knowledge_point_id].source_chunk_id].end_page] if points.get(row.knowledge_point_id) and points[row.knowledge_point_id].source_chunk_id in chunks else None), "mastery": row.mastery, "evidence_status": row.evidence_status, "score_rate": row.score_rate, "valid_answer_count": row.valid_answer_count, "evidence": row.evidence_json} for row in rows]}


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
