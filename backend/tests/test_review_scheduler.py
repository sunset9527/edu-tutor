"""v1.4 遗忘与复习状态机的回归测试。"""

from datetime import datetime, timedelta

import pytest

from app.models.memory import Memory, ReviewPlan
from app.services.memory import forgetting
from app.services.memory.forgetting import ReviewScheduler, retention_weight


class InMemorySession:
    """调度器所需的最小会话实现，避免测试依赖本机 MySQL 连接。"""

    def __init__(self, *objects):
        self.objects = {(type(obj), obj.id): obj for obj in objects}
        self.added = []

    def get(self, model, object_id):
        return self.objects.get((model, object_id))

    def add(self, obj):
        if obj.id is None:
            obj.id = max(
                (item.id for item in self.objects.values() if type(item) is type(obj)),
                default=0,
            ) + 1
        self.objects[(type(obj), obj.id)] = obj
        self.added.append(obj)

    def commit(self):
        pass


@pytest.fixture(autouse=True)
def use_default_decay_lambda(monkeypatch):
    """状态机单测不依赖动态配置表及本机 MySQL。"""
    monkeypatch.setattr(
        forgetting.settings_service,
        "get_float",
        lambda _key, default: default,
    )


def test_unreviewed_memory_decays_from_created_at():
    """从未复习的记忆也必须从创建时间开始遗忘。"""
    now = datetime(2026, 10, 11, 12, 0, 0)
    created_at = now - timedelta(days=7)

    weight = retention_weight(
        strength=0.6,
        last_reviewed_at=None,
        created_at=created_at,
        now=now,
    )

    assert weight < 0.6


def test_successful_review_creates_next_pending_plan():
    """成功复习后，旧计划完成且生成下一次待复习计划。"""
    now = datetime(2026, 10, 11, 12, 0, 0)
    memory = Memory(
        id=11,
        student_id=7,
        memory_type="episodic",
        content="用于验证复习状态机的测试记忆",
        strength=0.6,
    )
    plan = ReviewPlan(
        id=21,
        student_id=7,
        target_type="memory",
        target_id=memory.id,
        interval_days=1,
        next_review_at=now - timedelta(minutes=1),
        status="pending",
    )
    db = InMemorySession(memory, plan)

    ReviewScheduler().mark_reviewed(db, plan.id, success=True, now=now)
    next_plan = next(
        item
        for item in db.added
        if isinstance(item, ReviewPlan) and item.status == "pending"
    )

    assert memory.last_reviewed_at == now
    assert plan.status == "done"
    assert next_plan.id != plan.id
    assert next_plan.interval_days == 2
    assert next_plan.next_review_at == now + timedelta(days=2)


def test_failed_review_keeps_plan_pending_and_records_review_time():
    """复习失败后保留同一待办、缩短间隔，并记录实际复习时间。"""
    now = datetime(2026, 10, 11, 12, 0, 0)
    memory = Memory(
        id=12,
        student_id=8,
        memory_type="episodic",
        content="用于验证复习状态机的测试记忆",
        strength=0.6,
    )
    plan = ReviewPlan(
        id=22,
        student_id=8,
        target_type="memory",
        target_id=memory.id,
        interval_days=4,
        next_review_at=now - timedelta(minutes=1),
        status="pending",
    )
    db = InMemorySession(memory, plan)
    ReviewScheduler().mark_reviewed(db, plan.id, success=False, now=now)

    assert memory.last_reviewed_at == now
    assert plan.status == "pending"
    assert plan.interval_days == 1
    assert plan.next_review_at == now + timedelta(days=1)


def test_three_successful_reviews_keep_a_pending_plan():
    memory = Memory(
        id=13,
        student_id=9,
        memory_type="episodic",
        content="连续复习测试",
        strength=0.6,
    )
    current = ReviewPlan(
        id=23,
        student_id=9,
        target_type="memory",
        target_id=memory.id,
        interval_days=1,
        next_review_at=datetime(2026, 10, 11, 12, 0, 0),
        status="pending",
    )
    db = InMemorySession(memory, current)
    scheduler = ReviewScheduler()

    for day in range(3):
        current = scheduler.mark_reviewed(
            db,
            current.id,
            success=True,
            now=datetime(2026, 10, 11 + day, 12, 0, 0),
        )

    assert current is not None
    assert current.status == "pending"
    assert current.interval_days == 8
