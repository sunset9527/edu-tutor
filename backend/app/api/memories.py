"""记忆复习 API：复习打卡 + 复习计划查询"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.memory import Memory, ReviewPlan
from app.services.memory.forgetting import ReviewScheduler

router = APIRouter(prefix="/api", tags=["memories"])


class ReviewRequest(BaseModel):
    success: bool = True


@router.post("/memories/{memory_id}/review")
def review_memory(
    memory_id: int, payload: ReviewRequest, db: Session = Depends(get_db)
):
    """复习打卡：成功则强度上升、间隔翻倍；失败则强度减半、间隔重置"""
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
    scheduler.mark_reviewed(db, plan.id, payload.success)

    memory = db.get(Memory, memory_id)
    return {
        "ok": True,
        "success": payload.success,
        "strength": round(memory.strength, 3) if memory else None,
        "next_interval_days": plan.interval_days,
        "next_review_at": str(plan.next_review_at),
    }


@router.get("/students/{student_id}/review-plans")
def review_plans(student_id: int, db: Session = Depends(get_db)):
    """到期待复习列表（含记忆内容与间隔）"""
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
    memory_id: int, payload: MemoryUpdate, db: Session = Depends(get_db)
):
    """编辑记忆内容/掌握度/状态（人工纠错闭环）"""
    memory = db.get(Memory, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    if payload.content is not None:
        memory.content = payload.content
    if payload.mastery is not None:
        memory.mastery = payload.mastery
    if payload.status is not None:
        memory.status = payload.status
        if payload.status == "archived":
            try:
                from app.services.memory.chroma_client import get_memory_collection
                get_memory_collection().delete(ids=[str(memory.id)])
            except Exception:
                pass
    db.commit()
    return {"ok": True, "id": memory.id, "status": memory.status}


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    """删除记忆（软删 archived + 清向量）"""
    memory = db.get(Memory, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    memory.status = "archived"
    db.commit()
    try:
        from app.services.memory.chroma_client import get_memory_collection
        get_memory_collection().delete(ids=[str(memory.id)])
    except Exception:
        pass
    return {"ok": True, "id": memory_id}

