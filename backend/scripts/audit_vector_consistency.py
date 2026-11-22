"""审计并可选修复 memories 与 Chroma memory_vectors 的一致性。"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.core.embeddings import embed_texts  # noqa: E402
from app.models.knowledge import KnowledgePoint  # noqa: E402
from app.models.knowledge_governance import (  # noqa: E402
    KnowledgeSourceChunk,
    KnowledgeVersion,
    Textbook,
)
from app.models.memory import Memory  # noqa: E402
from app.services.knowledge.chroma_client import get_knowledge_collection  # noqa: E402
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


def _display_vector_id(value: str):
    return int(value) if str(value).isdigit() else str(value)


def json_safe(value):
    """将 Chroma/NumPy 结果递归变为可写入 JSON 的备份快照。"""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    return value


def sequence_or_empty(value):
    """只把 None 转为空序列，避免 NumPy 数组的歧义布尔判断。"""
    return [] if value is None else value


def normalize_embedding_batch(embeddings) -> list[list[float]]:
    """统一为 Python float list，避免 Chroma 拒绝 mixed list/ndarray batch。"""
    return [list(json_safe(embedding)) for embedding in embeddings]


def build_knowledge_consistency_report(
    mysql_points: list[dict], chroma_entries: dict[str, dict]
) -> dict[str, list]:
    """审计知识点向量是否完整携带教材、版本和来源 metadata。"""
    points = {str(row["id"]): row for row in mysql_points}
    point_ids = set(points)
    vector_ids = set(chroma_entries)
    metadata_errors = []
    for point_id in sorted(point_ids & vector_ids, key=lambda value: int(value)):
        row = points[point_id]
        metadata = chroma_entries[point_id].get("metadata") or {}
        if any(
            metadata.get(field) != row.get(field)
            for field in (
                "textbook_id",
                "version_id",
                "source_chunk_id",
                "subject",
                "grade",
            )
        ):
            metadata_errors.append(_display_vector_id(point_id))
    return {
        "missing_vector_ids": [
            _display_vector_id(value)
            for value in sorted(point_ids - vector_ids, key=lambda value: int(value))
        ],
        "orphan_vector_ids": [
            _display_vector_id(value)
            for value in sorted(
                vector_ids - point_ids,
                key=lambda value: (not str(value).isdigit(), str(value)),
            )
        ],
        "metadata_error_ids": metadata_errors,
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


def _knowledge_snapshots(db, collection):
    rows = (
        db.query(KnowledgePoint, KnowledgeVersion, Textbook, KnowledgeSourceChunk)
        .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgePoint.version_id)
        .join(Textbook, Textbook.id == KnowledgeVersion.textbook_id)
        .outerjoin(
            KnowledgeSourceChunk,
            KnowledgeSourceChunk.id == KnowledgePoint.source_chunk_id,
        )
        .all()
    )
    mysql_points = [
        {
            "id": point.id,
            "textbook_id": textbook.id,
            "version_id": version.id,
            "source_chunk_id": point.source_chunk_id,
            "subject": point.subject,
            "grade": point.grade,
            "content": point.content_md or "",
            "status": version.status,
            "start_page": chunk.start_page if chunk else None,
            "end_page": chunk.end_page if chunk else None,
        }
        for point, version, textbook, chunk in rows
    ]
    raw = collection.get(include=["documents", "metadatas"])
    ids = raw.get("ids") or []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []
    entries = {
        str(vector_id): {"document": document, "metadata": metadata or {}}
        for vector_id, document, metadata in zip(ids, documents, metadatas)
    }
    return mysql_points, entries


def _knowledge_metadata(row: dict) -> dict:
    """构建 Chroma 支持的 metadata；来源缺口不写入 None。"""
    metadata = {
        "textbook_id": row["textbook_id"],
        "version_id": row["version_id"],
        "subject": row["subject"],
        "grade": row["grade"],
        "status": row.get("status") or "active",
    }
    if row.get("source_chunk_id") is not None:
        metadata.update(
            {
                "source_chunk_id": row["source_chunk_id"],
                "start_page": row.get("start_page"),
                "end_page": row.get("end_page"),
            }
        )
    return metadata


def repair_knowledge_vectors(
    collection,
    mysql_points: list[dict],
    chroma_entries: dict[str, dict],
    report: dict[str, list],
    *,
    backup_dir: Path,
) -> dict:
    """备份孤儿向量，并修复版本化知识的向量/metadata。"""
    backup_dir.mkdir(parents=True, exist_ok=True)
    orphan_ids = [str(value) for value in report["orphan_vector_ids"]]
    backup_path = None
    if orphan_ids:
        raw = collection.get(
            ids=orphan_ids,
            include=["embeddings", "documents", "metadatas"],
        )
        backup_path = backup_dir / (
            "knowledge-vector-orphans-"
            + datetime.now().strftime("%Y%m%d-%H%M%S")
            + ".json.gz"
        )
        with gzip.open(backup_path, "wt", encoding="utf-8") as handle:
            json.dump(json_safe(raw), handle, ensure_ascii=False)
        collection.delete(ids=orphan_ids)

    rows_by_id = {str(row["id"]): row for row in mysql_points}
    repair_ids = sorted(
        {
            *[str(value) for value in report["missing_vector_ids"]],
            *[str(value) for value in report["metadata_error_ids"]],
        },
        key=int,
    )
    existing = collection.get(
        ids=[value for value in repair_ids if value in chroma_entries],
        include=["embeddings"],
    ) if repair_ids else {"ids": [], "embeddings": []}
    existing_embeddings = dict(
        zip(
            sequence_or_empty(existing.get("ids")),
            sequence_or_empty(existing.get("embeddings")),
        )
    )
    rows = [rows_by_id[value] for value in repair_ids]
    missing_rows = [row for row in rows if str(row["id"]) not in existing_embeddings]
    new_embeddings = embed_texts([row["content"] for row in missing_rows]) if missing_rows else []
    new_embeddings_by_id = {
        str(row["id"]): embedding for row, embedding in zip(missing_rows, new_embeddings)
    }
    for start in range(0, len(rows), 128):
        batch = rows[start:start + 128]
        collection.upsert(
            ids=[str(row["id"]) for row in batch],
            embeddings=normalize_embedding_batch(
                [
                    existing_embeddings[str(row["id"])]
                    if str(row["id"]) in existing_embeddings
                    else new_embeddings_by_id[str(row["id"])]
                    for row in batch
                ]
            ),
            documents=[row["content"] for row in batch],
            metadatas=[_knowledge_metadata(row) for row in batch],
        )
    return {
        "backup_path": str(backup_path) if backup_path else None,
        "deleted_orphan_count": len(orphan_ids),
        "rewritten_vector_count": len(rows),
        "reembedded_missing_count": len(missing_rows),
    }


def audit(*, apply: bool = False, apply_knowledge: bool = False, backup_dir: Path | None = None) -> dict:
    db = SessionLocal()
    collection = get_memory_collection()
    knowledge_collection = get_knowledge_collection()
    try:
        memories, mysql_rows, chroma_entries, valid_kp_ids = _snapshots(db, collection)
        report = build_consistency_report(mysql_rows, chroma_entries, valid_kp_ids)
        knowledge_rows, knowledge_entries = _knowledge_snapshots(
            db, knowledge_collection
        )
        knowledge_report = build_knowledge_consistency_report(
            knowledge_rows, knowledge_entries
        )
        if not apply and not apply_knowledge:
            return {
                "mode": "dry-run",
                **report,
                "knowledge_vectors": knowledge_report,
            }

        by_id = {memory.id: memory for memory in memories}
        if apply:
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
        knowledge_repair = None
        if apply_knowledge:
            knowledge_repair = repair_knowledge_vectors(
                knowledge_collection,
                knowledge_rows,
                knowledge_entries,
                knowledge_report,
                backup_dir=backup_dir or Path("data/audit_backups"),
            )

        _, mysql_rows, chroma_entries, valid_kp_ids = _snapshots(db, collection)
        knowledge_rows, knowledge_entries = _knowledge_snapshots(
            db, knowledge_collection
        )
        return {
            "mode": "apply",
            "before": report,
            "after": build_consistency_report(mysql_rows, chroma_entries, valid_kp_ids),
            "knowledge_vectors": build_knowledge_consistency_report(
                knowledge_rows, knowledge_entries
            ),
            "knowledge_repair": knowledge_repair,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="执行修复；默认只读审计")
    parser.add_argument(
        "--apply-knowledge",
        action="store_true",
        help="备份后修复知识向量；默认只读审计",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("data/audit_backups"),
        help="知识孤儿向量的 gzip 备份目录",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            audit(
                apply=args.apply,
                apply_knowledge=args.apply_knowledge,
                backup_dir=args.backup_dir,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
