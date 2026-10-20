"""记忆人工编辑的数据库与向量同步通道。"""

from dataclasses import dataclass
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.services.memory.storage import delete_memory_vector, upsert_memory_vector


class MemoryEditError(RuntimeError):
    pass


@dataclass
class MemoryEditResult:
    before: dict
    after: dict
    vector_changed: bool
    vector_snapshot: SimpleNamespace

    def as_reference(self) -> dict:
        return {"before": self.before, "after": self.after}


def _snapshot(memory: Memory) -> SimpleNamespace:
    return SimpleNamespace(
        id=memory.id,
        student_id=memory.student_id,
        memory_type=memory.memory_type,
        content=memory.content,
        structured_data=dict(memory.structured_data or {}),
        mastery=memory.mastery,
        status=memory.status,
    )


def restore_memory_vector(result: MemoryEditResult) -> None:
    """数据库提交失败后，将向量恢复到编辑前状态。"""
    if not result.vector_changed:
        return
    if result.vector_snapshot.status == "active":
        upsert_memory_vector(result.vector_snapshot)
    else:
        delete_memory_vector(result.vector_snapshot.id)


def edit_memory(
    db: Session,
    memory: Memory,
    changes: dict,
    *,
    commit: bool = True,
) -> MemoryEditResult:
    """应用允许字段，并保持向量与数据库一致。

    ``commit=False`` 用于纠错工单：由调用方把记忆变更与工单状态放在同一事务提交。
    """
    before = _snapshot(memory)
    if "content" in changes and changes["content"] is not None:
        memory.content = str(changes["content"])
    if "mastery" in changes and changes["mastery"] is not None:
        memory.mastery = str(changes["mastery"])
    if "status" in changes and changes["status"] is not None:
        memory.status = str(changes["status"])

    vector_changed = memory.content != before.content or memory.status != before.status
    result = MemoryEditResult(
        before={
            "content": before.content,
            "mastery": before.mastery,
            "status": before.status,
        },
        after={
            "content": memory.content,
            "mastery": memory.mastery,
            "status": memory.status,
        },
        vector_changed=vector_changed,
        vector_snapshot=before,
    )
    try:
        if vector_changed:
            if memory.status == "active":
                upsert_memory_vector(memory)
            else:
                delete_memory_vector(memory.id)
        if commit:
            db.commit()
    except Exception as exc:
        db.rollback()
        try:
            restore_memory_vector(result)
        except Exception:  # noqa: BLE001
            pass
        raise MemoryEditError("记忆与向量同步失败") from exc
    return result
