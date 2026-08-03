"""遗忘曲线与复习调度（v0.3，SM-2 简化模型）

- 记忆保留率：R = strength × e^(-λt)
  strength ∈ [0,1]（初始 0.6），λ 为遗忘速率（默认 0.1）
- 复习成功：strength = min(1, strength×1.3+0.05)，间隔 ×2（1→2→4→8…）
- 复习失败：strength = strength×0.5，间隔重置为 1
- 检索权重 = 保留率（retriever 按此重排）
"""
import logging
import math
from datetime import datetime, timedelta

from app.core.config import settings
from app.services import settings_service
from app.models.memory import Memory, ReviewPlan

logger = logging.getLogger(__name__)


def calculate_retention(
    strength: float, days: float, lambda_: float | None = None
) -> float:
    """记忆保留率 R = strength × e^(-λt)，∈ [0,1]"""
    lam = lambda_ if lambda_ is not None else settings_service.get_float("decay_lambda", settings.decay_lambda)
    if days < 0:
        days = 0.0
    return max(0.0, min(1.0, strength * math.exp(-lam * days)))


def review_success(strength: float, interval_days: int) -> tuple[float, int]:
    """复习成功：强度上升，间隔翻倍"""
    new_strength = min(1.0, strength * 1.3 + 0.05)
    return new_strength, max(1, interval_days * 2)


def review_failure(strength: float) -> tuple[float, int]:
    """复习失败：强度减半，间隔重置为 1 天"""
    return strength * 0.5, 1


def retention_weight(
    strength: float, last_reviewed_at: datetime | None, now: datetime | None = None
) -> float:
    """记忆检索权重（基于上次复习/创建时间）"""
    now = now or datetime.now()
    base_time = last_reviewed_at or now
    days = max(0.0, (now - base_time).total_seconds() / 86400.0)
    return calculate_retention(strength, days)


class ReviewScheduler:
    """复习计划管理（review_plans 表）"""

    def create_plan(
        self,
        db,
        student_id: int,
        target_type: str,
        target_id: int,
        interval_days: int | None = None,
    ) -> ReviewPlan:
        """为记忆/知识点创建复习计划（默认 1 天后首次复习）"""
        interval = interval_days or settings_service.get_int("review_interval_base", settings.review_interval_base)
        plan = ReviewPlan(
            student_id=student_id,
            target_type=target_type,
            target_id=target_id,
            interval_days=interval,
            next_review_at=datetime.now() + timedelta(days=interval),
            status="pending",
        )
        db.add(plan)
        return plan

    def mark_reviewed(self, db, plan_id: int, success: bool) -> None:
        """复习打卡：更新间隔/强度，安排下次复习"""
        plan = db.get(ReviewPlan, plan_id)
        if not plan:
            return

        # 更新关联记忆强度
        if plan.target_type == "memory":
            memory = db.get(Memory, plan.target_id)
            if memory:
                if success:
                    memory.strength, plan.interval_days = review_success(
                        memory.strength, plan.interval_days
                    )
                else:
                    memory.strength, plan.interval_days = review_failure(memory.strength)

        plan.next_review_at = datetime.now() + timedelta(days=plan.interval_days)
        plan.status = "pending" if not success else "done"
        db.commit()

    def get_due_reviews(self, db, student_id: int) -> list[ReviewPlan]:
        """到期待复习列表"""
        now = datetime.now()
        return (
            db.query(ReviewPlan)
            .filter(
                ReviewPlan.student_id == student_id,
                ReviewPlan.status == "pending",
                ReviewPlan.next_review_at <= now,
            )
            .order_by(ReviewPlan.next_review_at)
            .all()
        )
