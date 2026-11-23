"""v1.8 学习目标的版本化创建服务。"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgePoint
from app.models.knowledge_governance import Textbook
from app.models.learning import LearningGoal, LearningGoalTarget, LearningGoalVersion


def create_learning_goal(
    db: Session,
    *,
    student_id: int,
    target_date: date,
    weekly_minutes: int,
    subject: str,
    target_level: str,
    target_knowledge_point_ids: list[int],
) -> LearningGoal:
    """创建学习目标并将首个版本固定到当前 active 知识版本。"""
    if target_date <= date.today():
        raise ValueError("目标日期必须晚于今天")
    if weekly_minutes <= 0:
        raise ValueError("每周可投入时间必须大于 0")
    unique_target_ids = list(dict.fromkeys(target_knowledge_point_ids))
    if not unique_target_ids:
        raise ValueError("至少选择一个目标知识点")

    points = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.id.in_(unique_target_ids))
        .order_by(KnowledgePoint.id)
        .all()
    )
    if len(points) != len(unique_target_ids):
        raise ValueError("目标知识点不存在")
    version_ids = {point.version_id for point in points}
    if len(version_ids) != 1 or None in version_ids:
        raise ValueError("目标知识点必须来自同一受控知识版本")
    if any(
        point.subject != subject or point.source_chunk_id is None or point.provenance_gap
        for point in points
    ):
        raise ValueError("目标知识点必须具有同学科的教材来源证据")

    knowledge_version_id = version_ids.pop()
    active_textbook = (
        db.query(Textbook)
        .filter(
            Textbook.active_version_id == knowledge_version_id,
            Textbook.subject == subject,
        )
        .one_or_none()
    )
    if active_textbook is None:
        raise ValueError("目标知识版本不是该学科当前 active 版本")

    goal = LearningGoal(student_id=student_id)
    db.add(goal)
    db.flush()
    version = LearningGoalVersion(
        goal_id=goal.id,
        version_no=1,
        knowledge_version_id=knowledge_version_id,
        target_date=target_date,
        weekly_minutes=weekly_minutes,
        subject=subject,
        target_level=target_level,
        status="active",
        change_reason="created",
    )
    db.add(version)
    db.flush()
    db.add_all(
        [
            LearningGoalTarget(goal_version_id=version.id, knowledge_point_id=point.id)
            for point in points
        ]
    )
    goal.current_version_id = version.id
    db.commit()
    db.refresh(goal)
    return goal


def append_learning_goal_version(
    db: Session,
    *,
    goal_id: int,
    target_date: date | None = None,
    weekly_minutes: int | None = None,
    target_level: str | None = None,
    target_knowledge_point_ids: list[int] | None = None,
    status: str | None = None,
    change_reason: str,
) -> LearningGoal:
    """追加学习目标版本，永不原地覆盖历史版本。"""
    goal = db.get(LearningGoal, goal_id)
    if goal is None or goal.current_version is None:
        raise ValueError("学习目标不存在或缺少当前版本")
    previous = goal.current_version
    next_target_date = target_date or previous.target_date
    next_weekly_minutes = weekly_minutes if weekly_minutes is not None else previous.weekly_minutes
    next_target_level = target_level or previous.target_level
    if next_target_date <= date.today():
        raise ValueError("目标日期必须晚于今天")
    if next_weekly_minutes <= 0:
        raise ValueError("每周可投入时间必须大于 0")

    if target_knowledge_point_ids is None:
        next_target_ids = [target.knowledge_point_id for target in previous.targets]
    else:
        next_target_ids = list(dict.fromkeys(target_knowledge_point_ids))
        if not next_target_ids:
            raise ValueError("至少选择一个目标知识点")
        points = db.query(KnowledgePoint).filter(KnowledgePoint.id.in_(next_target_ids)).all()
        if len(points) != len(next_target_ids):
            raise ValueError("目标知识点不存在")
        if any(
            point.version_id != previous.knowledge_version_id
            or point.subject != previous.subject
            or point.source_chunk_id is None
            or point.provenance_gap
            for point in points
        ):
            raise ValueError("新目标知识点必须来自当前目标固定知识版本且具有来源证据")

    next_version = LearningGoalVersion(
        goal_id=goal.id,
        version_no=previous.version_no + 1,
        knowledge_version_id=previous.knowledge_version_id,
        target_date=next_target_date,
        weekly_minutes=next_weekly_minutes,
        subject=previous.subject,
        target_level=next_target_level,
        status=status or previous.status,
        change_reason=change_reason,
    )
    db.add(next_version)
    db.flush()
    db.add_all(
        [
            LearningGoalTarget(
                goal_version_id=next_version.id,
                knowledge_point_id=knowledge_point_id,
            )
            for knowledge_point_id in next_target_ids
        ]
    )
    goal.current_version_id = next_version.id
    db.commit()
    db.refresh(goal)
    return goal
