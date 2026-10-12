"""审计并可选修复 memories 与 Chroma memory_vectors 的一致性。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.knowledge import KnowledgePoint  # noqa: E402
from app.models.memory import Memory  # noqa: E402
from app.services.memory.chroma_client import get_memory_collection  # noqa: E402
from app.services.memory.storage import (  # noqa: E402
    MemoryStorage,
    delete_memory_vector,
    upsert_memory_vector,
)


def build_consistency_report(
    mysql_memories: list[dict],
    chroma_entries: dict[str, dict],
    valid_knowledge_point_ids: set[int],
) -> dict[str, list[int]]:
    """根据两侧快照生成可序列化的问题清单。"""
    active = {int(row["id"]): row for row in mysql_memories if row["status"] == "active"}
    vector_ids = {int(value) for value in chroma_entries}
    active_ids = set(active)
    metadata_errors: list[int] = []
    for memory_id in sorted(active_ids & vector_ids):
        row = active[memory_id]
        entry = chroma_entries[str(memory_id)]
        metadata = entry.get("metadata") or {}
        if (
            entry.get("document") != row["content"]
            or metadata.get("student_id") != row["student_id"]
            or metadata.get("memory_type") != row["memory_type"]
            or metadata.get("predicate") != row["predicate"]
        ):
            metadata_errors.append(memory_id)

    invalid_links = sorted(
        row["id"]
        for row in mysql_memories
        if row.get("knowledge_point_id") is not None
        and row["knowledge_point_id"] not in valid_knowledge_point_ids
    )
    return {
        "missing_vector_ids": sorted(active_ids - vector_ids),
        "orphan_vector_ids": sorted(vector_ids - active_ids),
        "metadata_error_ids": metadata_errors,
        "invalid_knowledge_link_ids": invalid_links,
    }


def _snapshots(db, collection):
    memories = db.query(Memory).all()
    mysql_rows = [
        {
            "id": m.id,
            "student_id": m.student_id,
            "memory_type": m.memory_type,
            "status": m.status,
            "content": m.content,
            "predicate": str((m.structured_data or {}).get("predicate") or "信息"),
            "knowledge_point_id": m.knowledge_point_id,
        }
        for m in memories
    ]
    raw = collection.get(include=["documents", "metadatas"])
    ids = raw.get("ids") or []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []
    chroma_entries = {
        str(vector_id): {"document": document, "metadata": metadata or {}}
        for vector_id, document, metadata in zip(ids, documents, metadatas)
    }
    valid_kp_ids = {row[0] for row in db.query(KnowledgePoint.id).all()}
    return memories, mysql_rows, chroma_entries, valid_kp_ids


def audit(*, apply: bool = False) -> dict:
    db = SessionLocal()
    collection = get_memory_collection()
    try:
        memories, mysql_rows, chroma_entries, valid_kp_ids = _snapshots(db, collection)
        report = build_consistency_report(mysql_rows, chroma_entries, valid_kp_ids)
        if not apply:
            return {"mode": "dry-run", **report}

        by_id = {memory.id: memory for memory in memories}
        for memory_id in report["missing_vector_ids"] + report["metadata_error_ids"]:
            upsert_memory_vector(by_id[memory_id], collection=collection)
        for memory_id in report["orphan_vector_ids"]:
            delete_memory_vector(memory_id, collection=collection)
        storage = MemoryStorage()
        storage.collection = collection
        for memory_id in report["invalid_knowledge_link_ids"]:
            memory = by_id[memory_id]
            memory.knowledge_point_id = None
            storage._link_knowledge_point(db, memory)
        db.commit()

        _, mysql_rows, chroma_entries, valid_kp_ids = _snapshots(db, collection)
        return {
            "mode": "apply",
            "before": report,
            "after": build_consistency_report(mysql_rows, chroma_entries, valid_kp_ids),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="执行修复；默认只读审计")
    args = parser.parse_args()
    print(json.dumps(audit(apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
