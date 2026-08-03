"""v0.3 遗忘曲线测试（纯函数，快）"""
from datetime import datetime, timedelta

from app.services.memory.forgetting import (
    calculate_retention,
    retention_weight,
    review_failure,
    review_success,
)


def test_retention_new_memory_is_full():
    """新记忆（0 天）保留率 = strength"""
    assert calculate_retention(0.6, 0) == 0.6


def test_retention_decays_over_time():
    """时间越长保留率越低"""
    r1 = calculate_retention(0.6, 1)
    r7 = calculate_retention(0.6, 7)
    assert r1 > r7
    assert 0 < r7 < 1


def test_retention_respects_lambda():
    """λ 越大忘得越快"""
    r_slow = calculate_retention(0.6, 7, lambda_=0.05)
    r_fast = calculate_retention(0.6, 7, lambda_=0.2)
    assert r_slow > r_fast


def test_review_success_boosts_strength():
    """复习成功：强度上升，间隔翻倍"""
    s, interval = review_success(0.6, 1)
    assert s > 0.6
    assert interval == 2
    s2, interval2 = review_success(0.9, 8)
    assert s2 <= 1.0
    assert interval2 == 16


def test_review_failure_halves_strength():
    """复习失败：强度减半，间隔重置"""
    s, interval = review_failure(0.6)
    assert abs(s - 0.3) < 1e-9
    assert interval == 1


def test_retention_weight_uses_last_review():
    """检索权重：最近复习过 → 权重更高"""
    now = datetime.now()
    reviewed_1d_ago = retention_weight(0.6, now - timedelta(days=1))
    reviewed_7d_ago = retention_weight(0.6, now - timedelta(days=7))
    assert reviewed_1d_ago > reviewed_7d_ago
