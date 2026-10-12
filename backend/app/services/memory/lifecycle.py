"""v1.5 记忆生命周期中的纯规则。"""

from datetime import datetime


MASTERY_LEVELS = ("不懂", "基本会", "熟练", "精通")


def transition_mastery(current: str | None, success: bool) -> str:
    """按一次可验证练习结果前进或后退一个掌握等级。"""
    try:
        index = MASTERY_LEVELS.index(current or "不懂")
    except ValueError:
        index = 0
    next_index = min(len(MASTERY_LEVELS) - 1, index + 1) if success else max(0, index - 1)
    return MASTERY_LEVELS[next_index]


def build_provenance(
    *,
    session_id: int | None,
    message_id: int | None,
    extraction_version: str,
    model_name: str,
    extracted_at: datetime | None = None,
) -> dict:
    """生成可序列化的记忆溯源字段。"""
    extracted_at = extracted_at or datetime.now()
    return {
        "source_session_id": session_id,
        "source_message_id": message_id,
        "extraction_version": extraction_version,
        "model_name": model_name,
        "extracted_at": extracted_at.isoformat(timespec="seconds"),
    }


def build_session_summary(
    messages: list[tuple[str, str]],
    *,
    max_chars: int = 500,
) -> str:
    """从已落库消息生成确定性的提取式摘要，便于重试与测试。"""
    labels = {"user": "学生", "assistant": "老师", "system": "系统"}
    parts = []
    for role, content in messages:
        cleaned = " ".join(str(content).split())
        if cleaned:
            parts.append(f"{labels.get(role, role)}：{cleaned}")
    summary = "；".join(parts)
    return summary[: max(0, max_chars)]
