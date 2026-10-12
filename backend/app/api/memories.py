"""记忆复习 API：复习打卡 + 复习计划查询"""
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.access import get_owned_memory, get_owned_student
from app.api.auth import require_current_user_id
from app.core.database import get_db
from app.models.memory import Memory, ReviewPlan
from app.services.memory.forgetting import ReviewScheduler
from app.services.memory.storage import delete_memory_vector, upsert_memory_vector

router = APIRouter(prefix="/api", tags=["memories"])


class ReviewRequest(BaseModel):
    success: bool = True


@router.post("/memories/{memory_id}/review")
def review_memory(
    memory_id: int,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """复习打卡：成功则强度上升、间隔翻倍；失败则强度减半、间隔重置"""
    memory = get_owned_memory(db, memory_id, user_id)
    plan = (
        db.query(ReviewPlan)
        .filter(
            ReviewPlan.target_type == "memory",
            ReviewPlan.target_id == memory_id,
            ReviewPlan.status == "pending",
        )
        .order_by(ReviewPlan.id.desc())
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="未找到该记忆的待复习计划")

    scheduler = ReviewScheduler()
    next_plan = scheduler.mark_reviewed(db, plan.id, payload.success)

    return {
        "ok": True,
        "success": payload.success,
        "strength": round(memory.strength, 3) if memory else None,
        "next_interval_days": next_plan.interval_days if next_plan else None,
        "next_review_at": str(next_plan.next_review_at) if next_plan else None,
    }


@router.get("/students/{student_id}/review-plans")
def review_plans(
    student_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """到期待复习列表（含记忆内容与间隔）"""
    get_owned_student(db, student_id, user_id)
    scheduler = ReviewScheduler()
    due = scheduler.get_due_reviews(db, student_id)
    result = []
    for plan in due:
        item = {
            "id": plan.id,
            "target_type": plan.target_type,
            "target_id": plan.target_id,
            "interval_days": plan.interval_days,
            "next_review_at": str(plan.next_review_at),
        }
        if plan.target_type == "memory":
            memory = db.get(Memory, plan.target_id)
            if memory:
                item["content"] = memory.content
                item["strength"] = round(memory.strength, 3)
        result.append(item)
    return result


class MemoryUpdate(BaseModel):
    content: str | None = None
    mastery: str | None = None
    status: str | None = None


@router.put("/memories/{memory_id}")
def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """编辑记忆内容/掌握度/状态（人工纠错闭环）"""
    memory = get_owned_memory(db, memory_id, user_id)
    old = SimpleNamespace(
        id=memory.id,
        student_id=memory.student_id,
        memory_type=memory.memory_type,
        content=memory.content,
        structured_data=dict(memory.structured_data or {}),
        status=memory.status,
    )
    vector_changed = False
    if payload.content is not None:
        memory.content = payload.content
        vector_changed = payload.content != old.content
    if payload.mastery is not None:
        memory.mastery = payload.mastery
    if payload.status is not None:
        memory.status = payload.status
        vector_changed = vector_changed or payload.status != old.status

    try:
        if vector_changed:
            if memory.status == "active":
                upsert_memory_vector(memory)
            else:
                delete_memory_vector(memory.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            if vector_changed:
                if old.status == "active":
                    upsert_memory_vector(old)
                else:
                    delete_memory_vector(old.id)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="记忆与向量同步失败") from exc
    return {"ok": True, "id": memory.id, "status": memory.status}


@router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """删除记忆（软删 archived + 清向量）"""
    memory = get_owned_memory(db, memory_id, user_id)
    old = SimpleNamespace(
        id=memory.id,
        student_id=memory.student_id,
        memory_type=memory.memory_type,
        content=memory.content,
        structured_data=dict(memory.structured_data or {}),
        status=memory.status,
    )
    memory.status = "archived"
    try:
        delete_memory_vector(memory.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            if old.status == "active":
                upsert_memory_vector(old)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="记忆与向量同步失败") from exc
    return {"ok": True, "id": memory_id}

