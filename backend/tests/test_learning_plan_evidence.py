"""v1.8 多来源掌握证据的时间与冲突解析契约。"""

from datetime import datetime, timedelta

from app.services.learning_plans import resolve_learning_evidence


def test_later_confirmed_diagnostic_overrides_older_memory_conflict():
    now = datetime.now()

    evidence = resolve_learning_evidence(
        diagnostic={"mastery": "不懂", "confirmed_at": now},
        memory={"mastery": "熟练", "observed_at": now - timedelta(days=1)},
    )

    assert evidence["mastery"] == "不懂"
    assert evidence["source"] == "diagnostic"
    assert evidence["conflict"] is True
    assert "较新的诊断" in evidence["reason"]


def test_unordered_conflict_uses_conservative_mastery():
    evidence = resolve_learning_evidence(
        diagnostic={"mastery": "熟练", "confirmed_at": None},
        memory={"mastery": "不懂", "observed_at": None},
    )

    assert evidence["mastery"] == "不懂"
    assert evidence["source"] == "conservative"
    assert evidence["conflict"] is True
