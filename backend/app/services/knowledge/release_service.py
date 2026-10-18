"""知识版本审核、一致性门禁、激活与无损回滚。"""

from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgePoint, KnowledgePointLink
from app.models.knowledge_governance import (
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    KnowledgeReview,
    KnowledgeReviewItem,
    KnowledgeSourceChunk,
    KnowledgeVersion,
    Textbook,
)
from app.services.knowledge.chroma_client import get_knowledge_collection


REQUIRED_REVIEW_TYPES = {
    "content",
    "formula",
    "knowledge_point",
    "difficulty",
    "prerequisite",
}


class ReleaseError(ValueError):
    pass


class ReleaseNotFoundError(ReleaseError):
    pass


class ReleaseConflictError(ReleaseError):
    pass


class ReleaseGateError(ReleaseError):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("；".join(issues))


def submit_review(
    db: Session,
    *,
    version_id: int,
    reviewer_id: int,
    conclusion: str,
    note: str | None,
    items: list[dict],
) -> KnowledgeReview:
    version = db.get(KnowledgeVersion, version_id)
    if not version:
        raise ReleaseNotFoundError("知识版本不存在")
    if version.status not in {"staged", "archived"}:
        raise ReleaseConflictError(f"版本状态 {version.status} 不允许审核")
    if conclusion not in {"passed", "rejected"}:
        raise ReleaseConflictError("审核结论必须为 passed 或 rejected")
    review = KnowledgeReview(
        version_id=version.id,
        reviewer_id=reviewer_id,
        conclusion=conclusion,
        note=note,
    )
    db.add(review)
    db.flush()
    for item in items:
        item_type = str(item.get("item_type") or "").strip()
        item_conclusion = str(item.get("conclusion") or "").strip()
        if not item_type or item_conclusion not in {"pass", "fail"}:
            raise ReleaseConflictError("抽检项类型或结论无效")
        db.add(
            KnowledgeReviewItem(
                review_id=review.id,
                item_type=item_type,
                target_type=str(item.get("target_type") or "version"),
                target_id=item.get("target_id"),
                original_value=item.get("original_value"),
                conclusion=item_conclusion,
                correction_note=item.get("correction_note"),
            )
        )
    if conclusion == "passed":
        version.reviewed_by = reviewer_id
        version.reviewed_at = datetime.now()
    db.commit()
    db.refresh(review)
    return review


def audit_version_consistency(
    db: Session, version_id: int, *, collection=None
) -> dict:
    version = db.get(KnowledgeVersion, version_id)
    if not version:
        raise ReleaseNotFoundError("知识版本不存在")
    textbook = db.get(Textbook, version.textbook_id)
    if not textbook:
        raise ReleaseNotFoundError("教材不存在")
    collection = collection or get_knowledge_collection()
    issues: list[str] = []

    task = (
        db.query(KnowledgeBuildTask)
        .filter(KnowledgeBuildTask.target_version_id == version.id)
        .order_by(KnowledgeBuildTask.id.desc())
        .first()
    )
    if not task or task.status != "succeeded" or task.failed_units:
        issues.append("构建任务未全部成功")
    elif (
        db.query(KnowledgeBuildUnit)
        .filter(
            KnowledgeBuildUnit.task_id == task.id,
            KnowledgeBuildUnit.status.notin_(("completed", "skipped")),
        )
        .count()
    ):
        issues.append("仍有未完成构建单元")

    points = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.version_id == version.id)
        .order_by(KnowledgePoint.id)
        .all()
    )
    chunks = {
        row.id: row
        for row in db.query(KnowledgeSourceChunk)
        .filter(KnowledgeSourceChunk.version_id == version.id)
        .all()
    }
    point_ids = {row.id for row in points}
    if not points:
        issues.append("版本没有知识点")
    for point in points:
        if not (point.content_md or "").strip():
            issues.append(f"知识点 {point.id} 缺少正文")
        if not (point.difficulty or "").strip():
            issues.append(f"知识点 {point.id} 缺少难度")
        if point.source_chunk_id not in chunks:
            issues.append(f"知识点 {point.id} 来源块不属于当前版本")

    cross_version_edges = (
        db.query(KnowledgePointLink)
        .filter(
            or_(
                KnowledgePointLink.source_kp_id.in_(point_ids or {-1}),
                KnowledgePointLink.target_kp_id.in_(point_ids or {-1}),
            )
        )
        .all()
    )
    for edge in cross_version_edges:
        if edge.source_kp_id not in point_ids or edge.target_kp_id not in point_ids:
            issues.append(f"图谱边 {edge.id} 跨越知识版本")

    if version.point_count != len(points):
        issues.append("版本知识点计数快照与 MySQL 不一致")
    if version.source_chunk_count != len(chunks):
        issues.append("版本来源块计数快照与 MySQL 不一致")

    scoped_raw = collection.get(
        where={"version_id": version.id}, include=["documents", "metadatas"]
    )
    expected_ids = {str(value) for value in point_ids}
    raw = collection.get(
        ids=sorted(expected_ids), include=["documents", "metadatas"]
    ) if expected_ids else {"ids": [], "metadatas": [], "documents": []}
    vector_ids = [str(value) for value in (raw.get("ids") or [])]
    metadatas = raw.get("metadatas") or []
    documents = raw.get("documents") or []
    if set(vector_ids) != expected_ids or len(vector_ids) != len(points):
        issues.append("MySQL 知识点数量或 ID 与 Chroma 向量不一致")
    scoped_vector_ids = [str(value) for value in (scoped_raw.get("ids") or [])]
    if set(scoped_vector_ids) != expected_ids:
        issues.append("Chroma 版本过滤结果与 MySQL 不一致")
    if version.vector_count != len(scoped_vector_ids):
        issues.append("版本向量计数快照与 Chroma 不一致")
    for vector_id, metadata, document in zip(vector_ids, metadatas, documents):
        metadata = metadata or {}
        point = next((row for row in points if str(row.id) == vector_id), None)
        if (
            point is None
            or metadata.get("textbook_id") != textbook.id
            or metadata.get("version_id") != version.id
            or metadata.get("source_chunk_id") != point.source_chunk_id
            or metadata.get("subject") != textbook.subject
            or metadata.get("grade") != textbook.grade
        ):
            issues.append(f"向量 {vector_id} metadata 与版本来源不一致")
        if point is not None and document != (point.content_md or ""):
            issues.append(f"向量 {vector_id} 正文与 MySQL 不一致")

    review = (
        db.query(KnowledgeReview)
        .filter(
            KnowledgeReview.version_id == version.id,
            KnowledgeReview.conclusion == "passed",
        )
        .order_by(KnowledgeReview.id.desc())
        .first()
    )
    if not review:
        issues.append("缺少通过的版本审核")
    else:
        passed_types = {
            row[0]
            for row in db.query(KnowledgeReviewItem.item_type)
            .filter(
                KnowledgeReviewItem.review_id == review.id,
                KnowledgeReviewItem.conclusion == "pass",
            )
            .all()
        }
        missing_types = sorted(REQUIRED_REVIEW_TYPES - passed_types)
        if missing_types:
            issues.append(f"审核抽检类型不完整: {', '.join(missing_types)}")

    return {
        "version_id": version.id,
        "mysql_point_count": len(points),
        "mysql_source_chunk_count": len(chunks),
        "chroma_vector_count": len(scoped_vector_ids),
        "issues": issues,
        "ok": not issues,
    }


def _locked_textbook(db: Session, textbook_id: int) -> Textbook:
    textbook = (
        db.query(Textbook)
        .filter(Textbook.id == textbook_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if not textbook:
        raise ReleaseNotFoundError("教材不存在")
    return textbook


def _check_expected_active(textbook: Textbook, expected_active_version_id: int | None):
    if textbook.active_version_id != expected_active_version_id:
        raise ReleaseConflictError(
            f"当前 active 版本已变更为 {textbook.active_version_id}"
        )


def activate_version(
    db: Session,
    *,
    version_id: int,
    admin_id: int,
    expected_active_version_id: int | None,
    collection=None,
) -> KnowledgeVersion:
    version = db.get(KnowledgeVersion, version_id)
    if not version:
        raise ReleaseNotFoundError("知识版本不存在")
    textbook = _locked_textbook(db, version.textbook_id)
    _check_expected_active(textbook, expected_active_version_id)
    if version.status not in {"staged", "archived"}:
        raise ReleaseConflictError(f"版本状态 {version.status} 不允许激活")
    report = audit_version_consistency(db, version.id, collection=collection)
    if report["issues"]:
        raise ReleaseGateError(report["issues"])

    active_versions = (
        db.query(KnowledgeVersion)
        .filter(
            KnowledgeVersion.textbook_id == textbook.id,
            KnowledgeVersion.status == "active",
            KnowledgeVersion.id != version.id,
        )
        .all()
    )
    for current in active_versions:
        current.status = "archived"
    version.status = "active"
    version.activated_by = admin_id
    version.activated_at = datetime.now()
    textbook.active_version_id = version.id
    db.commit()
    db.refresh(version)
    return version


def rollback_textbook(
    db: Session,
    *,
    textbook_id: int,
    target_version_id: int,
    admin_id: int,
    expected_active_version_id: int | None,
    collection=None,
) -> KnowledgeVersion:
    del collection  # 回滚只切换已发布历史指针，不重建或删除向量。
    textbook = _locked_textbook(db, textbook_id)
    _check_expected_active(textbook, expected_active_version_id)
    target = db.get(KnowledgeVersion, target_version_id)
    if not target or target.textbook_id != textbook.id:
        raise ReleaseNotFoundError("目标历史版本不存在")
    if target.status not in {"archived", "active"}:
        raise ReleaseConflictError("只能回滚到曾经激活的历史版本")
    if textbook.active_version_id == target.id:
        return target
    current = db.get(KnowledgeVersion, textbook.active_version_id)
    if current:
        current.status = "archived"
    target.status = "active"
    target.activated_by = admin_id
    target.activated_at = datetime.now()
    textbook.active_version_id = target.id
    db.commit()
    db.refresh(target)
    return target
