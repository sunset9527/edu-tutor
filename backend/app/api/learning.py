"""v1.8 学习目标与诊断 API。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.access import get_owned_student
from app.api.auth import require_current_user_id
from app.core.database import get_db
from app.models.learning import LearningGoal
from app.services.learning_goals import create_learning_goal


router = APIRouter(prefix="/api/learning", tags=["learning"])


class LearningGoalCreate(BaseModel):
    student_id: int
    target_date: date
    weekly_minutes: int = Field(gt=0, le=10_080)
    subject: str = Field(min_length=1, max_length=20)
    target_level: str = Field(min_length=1, max_length=20)
    target_knowledge_point_ids: list[int] = Field(min_length=1)


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
