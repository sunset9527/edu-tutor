"""v1.6 学习事件与可追溯时间序列测试。"""

from datetime import datetime
from types import SimpleNamespace

from app.services.learning_events import build_report_timeline


def test_report_timeline_aggregates_real_events_and_keeps_ids():
    events = [
        SimpleNamespace(
            id=1,
            event_type="mastery_changed",
            occurred_at=datetime(2026, 10, 10, 9, 0),
            payload={"from": "不懂", "to": "基本会"},
        ),
        SimpleNamespace(
            id=2,
            event_type="wrong_question_added",
            occurred_at=datetime(2026, 10, 10, 10, 0),
            payload={},
        ),
        SimpleNamespace(
            id=3,
            event_type="review_succeeded",
            occurred_at=datetime(2026, 10, 11, 9, 0),
            payload={},
        ),
        SimpleNamespace(
            id=4,
            event_type="review_failed",
            occurred_at=datetime(2026, 10, 11, 10, 0),
            payload={},
        ),
    ]

    timeline = build_report_timeline(events)

    assert timeline == [
        {
            "date": "2026-10-10",
            "mastery_changes": 1,
            "wrong_added": 1,
            "wrong_mastered": 0,
            "review_succeeded": 0,
            "review_failed": 0,
            "review_completion_rate": None,
            "event_ids": [1, 2],
        },
        {
            "date": "2026-10-11",
            "mastery_changes": 0,
            "wrong_added": 0,
            "wrong_mastered": 0,
            "review_succeeded": 1,
            "review_failed": 1,
            "review_completion_rate": 0.5,
            "event_ids": [3, 4],
        },
    ]
