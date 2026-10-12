"""v1.5 记忆评分、状态更新与会话摘要单元测试。"""

from datetime import datetime, timedelta

import pytest

from app.services.memory.lifecycle import (
    build_provenance,
    build_session_summary,
    transition_mastery,
)
from app.services.memory.retriever import normalize_weights, score_memory_candidate


def test_retrieval_score_uses_all_components_and_normalized_weights():
    weights = normalize_weights(
        {"similarity": 4, "recency": 2, "retention": 3, "confidence": 1}
    )

    result = score_memory_candidate(
        similarity=0.8,
        recency=0.5,
        retention=0.6,
        confidence=0.9,
        weights=weights,
    )

    assert sum(weights.values()) == pytest.approx(1.0)
    assert result == pytest.approx(0.69)


def test_zero_retrieval_weights_fall_back_to_equal_weights():
    assert normalize_weights(
        {"similarity": 0, "recency": 0, "retention": 0, "confidence": 0}
    ) == {
        "similarity": 0.25,
        "recency": 0.25,
        "retention": 0.25,
        "confidence": 0.25,
    }


@pytest.mark.parametrize(
    ("current", "success", "expected"),
    [
        ("不懂", True, "基本会"),
        ("基本会", True, "熟练"),
        ("熟练", True, "精通"),
        ("精通", True, "精通"),
        ("精通", False, "熟练"),
        ("熟练", False, "基本会"),
        ("基本会", False, "不懂"),
        ("不懂", False, "不懂"),
    ],
)
def test_mastery_transition_is_bounded(current, success, expected):
    assert transition_mastery(current, success) == expected


def test_session_summary_is_deterministic_and_bounded():
    messages = [
        ("user", "我不理解一元一次方程移项。"),
        ("assistant", "先把含未知数的项放在等号左边。"),
        ("user", "我明白了，移项要变号。"),
    ]

    summary = build_session_summary(messages, max_chars=45)

    assert summary.startswith("学生：我不理解一元一次方程移项。")
    assert len(summary) <= 45
    assert summary == build_session_summary(messages, max_chars=45)


def test_provenance_records_actual_source_and_extractor():
    now = datetime(2026, 10, 12, 10, 30, 0)
    provenance = build_provenance(
        session_id=7,
        message_id=19,
        extraction_version="v1.5",
        model_name="deepseek-chat",
        extracted_at=now,
    )

    assert provenance == {
        "source_session_id": 7,
        "source_message_id": 19,
        "extraction_version": "v1.5",
        "model_name": "deepseek-chat",
        "extracted_at": "2026-10-12T10:30:00",
    }


def test_recency_changes_score_direction():
    now = datetime(2026, 10, 12, 12, 0, 0)
    recent = now - timedelta(days=1)
    old = now - timedelta(days=30)

    from app.services.memory.retriever import recency_score

    assert recency_score(recent, now=now, decay_days=14) > recency_score(
        old, now=now, decay_days=14
    )
