"""v1.4 记忆语义、报告统计和向量审计规则测试。"""

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.api import students
from app.services.memory import storage


def test_three_weaknesses_do_not_conflict():
    existing = {
        "predicate": "薄弱点",
        "object": "解方程移项",
        "knowledge_point_id": 11,
    }

    assert not storage.facts_conflict(
        existing,
        {"predicate": "薄弱点", "object": "函数图像", "knowledge_point_id": 12},
    )
    assert not storage.facts_conflict(
        existing,
        {"predicate": "薄弱点", "object": "几何证明", "knowledge_point_id": 13},
    )


def test_single_value_fact_conflicts_when_value_changes():
    assert storage.facts_conflict(
        {"predicate": "学习偏好", "object": "生活化例子"},
        {"predicate": "学习偏好", "object": "图示讲解"},
    )


def test_mastered_conflicts_with_weakness_for_same_knowledge_point():
    assert storage.facts_conflict(
        {"predicate": "薄弱点", "object": "一元一次方程", "knowledge_point_id": 21},
        {"predicate": "已掌握", "object": "一元一次方程", "knowledge_point_id": 21},
    )


def test_confidence_threshold_controls_write():
    assert not storage.is_memory_candidate_accepted(0.49, 0.5)
    assert storage.is_memory_candidate_accepted(0.5, 0.5)


def test_report_counts_only_pending_plans_that_are_due():
    now = datetime(2026, 10, 11, 12, 0, 0)
    plans = [
        SimpleNamespace(status="pending", next_review_at=now - timedelta(minutes=1)),
        SimpleNamespace(status="pending", next_review_at=now + timedelta(days=1)),
        SimpleNamespace(status="done", next_review_at=now - timedelta(days=1)),
    ]

    assert students.summarize_review_plans(plans, now=now) == {
        "total": 3,
        "due": 1,
        "done": 1,
        "pending": 2,
    }
