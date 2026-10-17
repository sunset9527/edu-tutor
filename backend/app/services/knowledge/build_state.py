"""知识构建任务的显式状态转换规则。"""


class InvalidBuildTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {"needs_attention", "succeeded", "failed", "cancelled"},
    "needs_attention": {"queued", "cancelled", "failed"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
}


def transition_task(task, new_status: str, *, stage: str | None = None) -> None:
    current = task.status
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidBuildTransition(f"非法构建状态转换: {current} -> {new_status}")
    task.status = new_status
    task.stage = stage
