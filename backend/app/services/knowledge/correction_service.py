"""纠错工单快照、审核与不可变知识版本修订。"""

import hashlib
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.embeddings import embed_texts
from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.models.knowledge_governance import (
    AnswerEvidenceLedger,
    CorrectionTicket,
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    KnowledgeSourceChunk,
    KnowledgeVersion,
    Textbook,
)
from app.models.memory import Memory
from app.models.session import Message, Session as TutorSession
from app.models.student import Student
from app.services.knowledge.chroma_client import get_knowledge_collection
from app.services.memory.editor import MemoryEditResult, edit_memory, restore_memory_vector


ALLOWED_CATEGORIES = {"knowledge", "question", "explanation", "memory"}


class CorrectionError(ValueError):
    pass


class CorrectionNotFoundError(CorrectionError):
    pass


class CorrectionConflictError(CorrectionError):
    pass


class CorrectionApplyError(CorrectionError):
    pass


def serialize_ticket(ticket: CorrectionTicket) -> dict:
    return {
        "id": ticket.id,
        "category": ticket.category,
        "target_type": ticket.target_type,
        "target_id": ticket.target_id,
        "original_value": ticket.original_value,
        "proposed_value": ticket.proposed_value,
        "reason": ticket.reason,
        "status": ticket.status,
        "submitted_by": ticket.submitted_by,
        "handled_by": ticket.handled_by,
        "handling_note": ticket.handling_note,
        "applied_version_id": ticket.applied_version_id,
        "result_reference": ticket.result_reference,
        "created_at": ticket.created_at,
        "handled_at": ticket.handled_at,
        "applied_at": ticket.applied_at,
    }


def create_ticket(
    db: Session,
    *,
    submitted_by: int,
    category: str,
    assistant_message_id: int,
    proposed_value: dict | None,
    reason: str,
    target_id: int | None = None,
) -> CorrectionTicket:
    if category not in ALLOWED_CATEGORIES:
        raise CorrectionConflictError("不支持的纠错分类")
    message = (
        db.query(Message)
        .join(TutorSession, TutorSession.id == Message.session_id)
        .join(Student, Student.id == TutorSession.student_id)
        .filter(
            Message.id == assistant_message_id,
            Message.role == "assistant",
            Student.user_id == submitted_by,
        )
        .first()
    )
    if not message:
        raise CorrectionNotFoundError("助手消息不存在")
    ledger = (
        db.query(AnswerEvidenceLedger)
        .filter(AnswerEvidenceLedger.assistant_message_id == message.id)
        .first()
    )
    if not ledger:
        raise CorrectionNotFoundError("回答证据账本不存在")

    target_type = "assistant_message"
    resolved_target_id = message.id
    target_snapshot = None
    if category == "knowledge":
        evidence = ledger.knowledge_evidence or []
        candidates = [row for row in evidence if row.get("adopted")]
        if target_id is not None:
            candidates = [
                row for row in candidates if row.get("knowledge_point_id") == target_id
            ]
        if not candidates:
            raise CorrectionConflictError("回答没有可纠错的已采用知识证据")
        resolved_target_id = int(candidates[0]["knowledge_point_id"])
        point = db.get(KnowledgePoint, resolved_target_id)
        if not point:
            raise CorrectionNotFoundError("知识点不存在")
        target_type = "knowledge_point"
        target_snapshot = {
            "id": point.id,
            "title": point.title,
            "content_md": point.content_md,
            "difficulty": point.difficulty,
            "version_id": point.version_id,
            "source_chunk_id": point.source_chunk_id,
        }
    elif category == "memory":
        evidence = ledger.memory_evidence or []
        candidates = evidence
        if target_id is not None:
            candidates = [row for row in evidence if row.get("memory_id") == target_id]
        if not candidates:
            raise CorrectionConflictError("回答没有可纠错的已采用记忆证据")
        resolved_target_id = int(candidates[0]["memory_id"])
        memory = (
            db.query(Memory)
            .join(Student, Student.id == Memory.student_id)
            .filter(Memory.id == resolved_target_id, Student.user_id == submitted_by)
            .first()
        )
        if not memory:
            raise CorrectionNotFoundError("记忆不存在")
        target_type = "memory"
        target_snapshot = {
            "id": memory.id,
            "content": memory.content,
            "mastery": memory.mastery,
            "status": memory.status,
            "structured_data": memory.structured_data,
        }

    ticket = CorrectionTicket(
        category=category,
        target_type=target_type,
        target_id=resolved_target_id,
        original_value={
            "assistant_message": {
                "id": message.id,
                "session_id": message.session_id,
                "content": message.content,
            },
            "evidence_ledger_id": ledger.id,
            "knowledge_evidence": ledger.knowledge_evidence or [],
            "memory_evidence": ledger.memory_evidence or [],
            "evidence_gap": ledger.evidence_gap or {},
            "target": target_snapshot,
        },
        proposed_value=proposed_value,
        reason=reason.strip(),
        status="pending",
        submitted_by=submitted_by,
    )
    if not ticket.reason:
        raise CorrectionConflictError("纠错原因不能为空")
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def reject_ticket(
    db: Session, *, ticket_id: int, admin_id: int, note: str
) -> CorrectionTicket:
    ticket = db.get(CorrectionTicket, ticket_id)
    if not ticket:
        raise CorrectionNotFoundError("纠错工单不存在")
    if ticket.status != "pending":
        raise CorrectionConflictError("只有 pending 工单可以驳回")
    if not note.strip():
        raise CorrectionConflictError("驳回原因不能为空")
    ticket.status = "rejected"
    ticket.handled_by = admin_id
    ticket.handling_note = note.strip()
    ticket.handled_at = datetime.now()
    db.commit()
    db.refresh(ticket)
    return ticket


def _revision_slug(version_id: int, old_point_id: int, title: str) -> str:
    digest = hashlib.sha256(
        f"correction:{version_id}:{old_point_id}:{title}".encode("utf-8")
    ).hexdigest()[:12]
    return f"{title[:150]}-v{version_id}-{digest}"


def _vector_metadata(
    *,
    textbook: Textbook,
    version: KnowledgeVersion,
    point: KnowledgePoint,
    source_chunk: KnowledgeSourceChunk | None,
) -> dict:
    metadata = {
        "textbook_id": textbook.id,
        "version_id": version.id,
        "subject": point.subject,
        "grade": point.grade or "",
        "status": "staged",
    }
    if source_chunk is not None:
        metadata.update(
            {
                "source_chunk_id": source_chunk.id,
                "start_page": source_chunk.start_page,
                "end_page": source_chunk.end_page,
            }
        )
    return metadata


def _clone_knowledge_version(
    db: Session,
    *,
    ticket: CorrectionTicket,
    admin_id: int,
    collection,
    embedder,
) -> KnowledgeVersion:
    target = db.get(KnowledgePoint, ticket.target_id)
    if not target or not target.version_id:
        raise CorrectionNotFoundError("目标知识点不存在或未版本化")
    parent = db.get(KnowledgeVersion, target.version_id)
    textbook = db.get(Textbook, parent.textbook_id) if parent else None
    if (
        not parent
        or not textbook
        or parent.status != "active"
        or textbook.active_version_id != parent.id
    ):
        raise CorrectionConflictError("只能修订当前 active 知识版本")
    latest = (
        db.query(func.max(KnowledgeVersion.version_no))
        .filter(KnowledgeVersion.textbook_id == textbook.id)
        .scalar()
        or 0
    )
    child = KnowledgeVersion(
        textbook_id=textbook.id,
        version_no=latest + 1,
        parent_version_id=parent.id,
        status="staged",
        created_by=admin_id,
    )
    db.add(child)
    db.flush()

    chunk_map: dict[int, KnowledgeSourceChunk] = {}
    parent_chunks = (
        db.query(KnowledgeSourceChunk)
        .filter(KnowledgeSourceChunk.version_id == parent.id)
        .order_by(KnowledgeSourceChunk.sequence)
        .all()
    )
    for old in parent_chunks:
        cloned = KnowledgeSourceChunk(
            version_id=child.id,
            sequence=old.sequence,
            start_page=old.start_page,
            end_page=old.end_page,
            region=old.region,
            raw_text=old.raw_text,
            content_hash=old.content_hash,
            parse_method=old.parse_method,
            parser_version=old.parser_version,
        )
        db.add(cloned)
        db.flush()
        chunk_map[old.id] = cloned

    proposed = ticket.proposed_value or {}
    parent_points = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.version_id == parent.id)
        .order_by(KnowledgePoint.id)
        .all()
    )
    point_map: dict[int, KnowledgePoint] = {}
    changed_old_ids: set[int] = set()
    for old in parent_points:
        changes = proposed if old.id == target.id else {}
        title = str(changes.get("title", old.title)).strip()
        content = str(changes.get("content_md", old.content_md or "")).strip()
        difficulty = str(changes.get("difficulty", old.difficulty)).strip()
        if not title or not content or not difficulty:
            raise CorrectionConflictError("修订后的标题、正文和难度不能为空")
        if changes:
            changed_old_ids.add(old.id)
        cloned = KnowledgePoint(
            subject=old.subject,
            grade=old.grade,
            chapter=old.chapter,
            title=title,
            slug=_revision_slug(child.id, old.id, title),
            content_md=content,
            difficulty=difficulty,
            version_id=child.id,
            source_chunk_id=(chunk_map.get(old.source_chunk_id).id if old.source_chunk_id else None),
            source_excerpt=old.source_excerpt,
            provenance_gap=old.provenance_gap,
        )
        db.add(cloned)
        db.flush()
        point_map[old.id] = cloned

    parent_ids = set(point_map)
    links = (
        db.query(KnowledgePointLink)
        .filter(
            KnowledgePointLink.source_kp_id.in_(parent_ids or {-1}),
            KnowledgePointLink.target_kp_id.in_(parent_ids or {-1}),
        )
        .all()
    )
    for link in links:
        db.add(
            KnowledgePointLink(
                source_kp_id=point_map[link.source_kp_id].id,
                target_kp_id=point_map[link.target_kp_id].id,
                link_type=link.link_type,
            )
        )
    db.flush()

    old_ids = [str(point.id) for point in parent_points]
    raw = collection.get(
        ids=old_ids, include=["embeddings", "documents", "metadatas"]
    )
    raw_embeddings = raw.get("embeddings")
    embeddings_by_id = {
        str(value): embedding
        for value, embedding in zip(
            raw.get("ids") or [],
            [] if raw_embeddings is None else raw_embeddings,
        )
    }
    new_ids = [str(point_map[old.id].id) for old in parent_points]
    documents = [point_map[old.id].content_md or "" for old in parent_points]
    embeddings = []
    for old, document in zip(parent_points, documents):
        if old.id in changed_old_ids or str(old.id) not in embeddings_by_id:
            embeddings.append(embedder([document])[0])
        else:
            embeddings.append(embeddings_by_id[str(old.id)])
    metadatas = [
        _vector_metadata(
            textbook=textbook,
            version=child,
            point=point_map[old.id],
            source_chunk=chunk_map.get(old.source_chunk_id),
        )
        for old in parent_points
    ]

    child.point_count = len(parent_points)
    child.edge_count = len(links)
    child.source_chunk_count = len(parent_chunks)
    child.vector_count = len(new_ids)
    task = KnowledgeBuildTask(
        textbook_id=textbook.id,
        target_version_id=child.id,
        requested_by=admin_id,
        idempotency_key=f"correction:{ticket.id}",
        status="succeeded",
        stage="staged",
        total_units=1,
        completed_units=1,
        failed_units=0,
        build_config={"kind": "correction", "ticket_id": ticket.id},
        finished_at=datetime.now(),
    )
    db.add(task)
    db.flush()
    db.add(
        KnowledgeBuildUnit(
            task_id=task.id,
            unit_type="revision_clone",
            sequence=1,
            status="completed",
            completed_at=datetime.now(),
            checkpoint={"ticket_id": ticket.id, "version_id": child.id},
        )
    )
    db.flush()
    # 向量写入放在最后：此前任一数据库步骤失败时，不会遗留孤儿向量。
    collection.upsert(
        ids=new_ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    return child


def _apply_memory_correction(db: Session, ticket: CorrectionTicket) -> MemoryEditResult:
    memory = db.get(Memory, ticket.target_id)
    if not memory:
        raise CorrectionNotFoundError("目标记忆不存在")
    return edit_memory(db, memory, ticket.proposed_value or {}, commit=False)


def accept_ticket(
    db: Session,
    *,
    ticket_id: int,
    admin_id: int,
    note: str,
    collection=None,
    embedder=None,
    memory_applier=None,
) -> CorrectionTicket:
    ticket = db.get(CorrectionTicket, ticket_id)
    if not ticket:
        raise CorrectionNotFoundError("纠错工单不存在")
    if ticket.status not in {"pending", "accepted"}:
        raise CorrectionConflictError("当前工单状态不允许接受")
    if not note.strip():
        raise CorrectionConflictError("处理说明不能为空")
    ticket.status = "accepted"
    ticket.handled_by = admin_id
    ticket.handling_note = note.strip()
    ticket.handled_at = datetime.now()
    db.commit()

    new_vector_ids: list[str] = []
    memory_edit: MemoryEditResult | None = None
    embedder = embedder or embed_texts
    try:
        ticket = db.get(CorrectionTicket, ticket_id)
        if ticket.category == "knowledge":
            collection = collection or get_knowledge_collection()
            child = _clone_knowledge_version(
                db,
                ticket=ticket,
                admin_id=admin_id,
                collection=collection,
                embedder=embedder,
            )
            db.flush()
            new_vector_ids = [
                str(row[0])
                for row in db.query(KnowledgePoint.id)
                .filter(KnowledgePoint.version_id == child.id)
                .all()
            ]
            ticket.applied_version_id = child.id
            ticket.result_reference = {
                "kind": "knowledge_version",
                "version_id": child.id,
                "parent_version_id": child.parent_version_id,
            }
        elif ticket.category == "memory":
            applier = memory_applier or _apply_memory_correction
            applied = applier(db, ticket)
            if isinstance(applied, MemoryEditResult):
                memory_edit = applied
                ticket.result_reference = applied.as_reference()
            else:
                ticket.result_reference = applied
        else:
            ticket.result_reference = {
                "kind": "review_only",
                "assistant_message_id": ticket.target_id,
            }
        ticket.status = "applied"
        ticket.applied_at = datetime.now()
        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception as exc:
        db.rollback()
        if new_vector_ids and collection is not None:
            try:
                collection.delete(ids=new_vector_ids)
            except Exception:  # noqa: BLE001
                pass
        if memory_edit is not None:
            try:
                restore_memory_vector(memory_edit)
            except Exception:  # noqa: BLE001
                pass
        ticket = db.get(CorrectionTicket, ticket_id)
        ticket.status = "accepted"
        ticket.result_reference = {"error": str(exc), "kind": "apply_failed"}
        ticket.handling_note = (
            (ticket.handling_note + "\n") if ticket.handling_note else ""
        ) + f"应用失败: {exc}"
        db.commit()
        raise CorrectionApplyError(str(exc)) from exc
