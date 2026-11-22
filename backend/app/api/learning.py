"""v1.8 学习目标与诊断 API。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.access import get_owned_student
from app.api.auth import require_current_user_id
from app.core.database import get_db
from app.models.learning import LearningGoal


router = APIRouter(prefix="/api/learning", tags=["learning"])


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
    version = goal.current_version
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
