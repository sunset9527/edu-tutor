"""学习事件写入与报告时间序列聚合。"""

from datetime import datetime

from app.models.learning_event import LearningEvent


EVENT_FIELDS = {
    "mastery_changed": "mastery_changes",
    "wrong_question_added": "wrong_added",
    "wrong_question_mastered": "wrong_mastered",
    "review_succeeded": "review_succeeded",
    "review_failed": "review_failed",
}


def add_learning_event(
    db,
    *,
    student_id: int,
    event_type: str,
    source_type: str | None = None,
    source_id: int | None = None,
    knowledge_point_id: int | None = None,
    payload: dict | None = None,
    occurred_at: datetime | None = None,
) -> LearningEvent:
    """把事件加入调用方事务，不在此处提交。"""
    event = LearningEvent(
        student_id=student_id,
        event_type=event_type,
        source_type=source_type,
        source_id=source_id,
        knowledge_point_id=knowledge_point_id,
        payload=payload or {},
        occurred_at=occurred_at or datetime.now(),
    )
    db.add(event)
    return event


def build_report_timeline(events) -> list[dict]:
    """按自然日聚合真实事件，并保留组成每个数字的记录 ID。"""
    days: dict[str, dict] = {}
    for event in sorted(events, key=lambda row: (row.occurred_at, row.id)):
        date = event.occurred_at.date().isoformat()
        point = days.setdefault(
            date,
            {
                "date": date,
                "mastery_changes": 0,
                "wrong_added": 0,
                "wrong_mastered": 0,
                "review_succeeded": 0,
                "review_failed": 0,
                "review_completion_rate": None,
                "event_ids": [],
            },
        )
        field = EVENT_FIELDS.get(event.event_type)
        if field:
            point[field] += 1
        point["event_ids"].append(event.id)

    for point in days.values():
        attempts = point["review_succeeded"] + point["review_failed"]
        if attempts:
            point["review_completion_rate"] = round(
                point["review_succeeded"] / attempts, 4
            )
    return list(days.values())
