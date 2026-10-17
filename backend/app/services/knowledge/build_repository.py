"""MySQL 持久化知识构建任务仓储。"""

from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.knowledge_governance import (
    KnowledgeBuildEvent,
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    Textbook,
)
from app.services.knowledge.build_state import transition_task


def append_event(
    db: Session,
    task: KnowledgeBuildTask,
    message: str,
    *,
    level: str = "info",
    unit_id: int | None = None,
) -> KnowledgeBuildEvent:
    event = KnowledgeBuildEvent(
        task_id=task.id,
        unit_id=unit_id,
        level=level,
        stage=task.stage,
        message=message,
    )
    db.add(event)
    return event


def create_build_task(
    db: Session,
    *,
    textbook_id: int,
    requested_by: int,
    idempotency_key: str,
    build_config: dict | None = None,
) -> tuple[KnowledgeBuildTask, bool]:
    existing = (
        db.query(KnowledgeBuildTask)
        .filter(KnowledgeBuildTask.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        return existing, False
    if not db.get(Textbook, textbook_id):
        raise ValueError("教材不存在")
    task = KnowledgeBuildTask(
        textbook_id=textbook_id,
        requested_by=requested_by,
        idempotency_key=idempotency_key,
        status="queued",
        build_config=build_config or {},
    )
    db.add(task)
    db.flush()
    append_event(db, task, "构建任务已创建")
    db.commit()
    db.refresh(task)
    return task, True


def claim_next_task(
    db: Session,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int = 60,
) -> KnowledgeBuildTask | None:
    task = (
        db.query(KnowledgeBuildTask)
        .filter(
            or_(
                KnowledgeBuildTask.status == "queued",
                and_(
                    KnowledgeBuildTask.status == "running",
                    KnowledgeBuildTask.lease_expires_at.isnot(None),
                    KnowledgeBuildTask.lease_expires_at < now,
                ),
            )
        )
        .order_by(KnowledgeBuildTask.created_at, KnowledgeBuildTask.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if task is None:
        db.rollback()
        return None
    reclaimed = task.status == "running"
    if task.status == "queued":
        transition_task(task, "running", stage="precheck")
    task.lease_owner = worker_id
    task.heartbeat_at = now
    task.lease_expires_at = now + timedelta(seconds=lease_seconds)
    task.started_at = task.started_at or now
    append_event(
        db,
        task,
        "过期租约已被重新认领" if reclaimed else "任务已被 worker 认领",
    )
    db.commit()
    db.refresh(task)
    return task


def heartbeat_task(
    db: Session,
    task_id: int,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int = 60,
) -> bool:
    task = db.get(KnowledgeBuildTask, task_id)
    if not task or task.status != "running" or task.lease_owner != worker_id:
        return False
    task.heartbeat_at = now
    task.lease_expires_at = now + timedelta(seconds=lease_seconds)
    db.commit()
    return True


def reset_failed_units(db: Session, task_id: int) -> int:
    task = db.get(KnowledgeBuildTask, task_id)
    if not task:
        raise ValueError("构建任务不存在")
    if task.status != "needs_attention":
        raise ValueError("只有待处理任务可以重试失败单元")
    units = (
        db.query(KnowledgeBuildUnit)
        .filter(
            KnowledgeBuildUnit.task_id == task.id,
            KnowledgeBuildUnit.status == "failed",
        )
        .all()
    )
    if not units:
        raise ValueError("任务没有失败单元")
    for unit in units:
        unit.status = "pending"
        unit.error_type = None
        unit.error_detail = None
        unit.started_at = None
        unit.completed_at = None
    transition_task(task, "queued", stage=None)
    task.retry_count += 1
    task.failed_units = 0
    task.error_summary = None
    task.lease_owner = None
    task.lease_expires_at = None
    task.heartbeat_at = None
    append_event(db, task, f"已重置 {len(units)} 个失败单元")
    db.commit()
    return len(units)
