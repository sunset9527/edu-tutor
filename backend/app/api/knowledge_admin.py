"""v1.7 教材与知识版本治理管理员接口。"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import require_admin_user_id
from app.core.database import get_db
from app.models.knowledge_governance import (
    KnowledgeBuildEvent,
    KnowledgeBuildTask,
    KnowledgeBuildUnit,
    KnowledgeReview,
    KnowledgeReviewItem,
    KnowledgeSourceChunk,
    KnowledgeVersion,
    Textbook,
)
from app.models.knowledge import KnowledgePoint
from app.services.knowledge.build_repository import (
    cancel_task,
    create_build_task,
    reset_failed_units,
    resume_task,
)
from app.services.knowledge.release_service import (
    ReleaseConflictError,
    ReleaseGateError,
    ReleaseNotFoundError,
    activate_version,
    rollback_textbook,
    submit_review,
)
from app.services.knowledge.textbook_service import (
    TextbookConflictError,
    TextbookValidationError,
    serialize_textbook,
    store_textbook_upload,
)


router = APIRouter(prefix="/api/admin", tags=["knowledge-admin"])


class BuildCreateRequest(BaseModel):
    group_size: int = Field(default=12, ge=1, le=100)
    use_ocr: bool = False


class ReviewItemRequest(BaseModel):
    item_type: str = Field(min_length=1, max_length=30)
    target_type: str = Field(default="version", min_length=1, max_length=30)
    target_id: int | None = None
    original_value: dict | None = None
    conclusion: str = Field(pattern="^(pass|fail)$")
    correction_note: str | None = None


class ReviewRequest(BaseModel):
    conclusion: str = Field(pattern="^(passed|rejected)$")
    note: str | None = None
    items: list[ReviewItemRequest] = Field(min_length=1)


class ActivateRequest(BaseModel):
    expected_active_version_id: int | None


class RollbackRequest(BaseModel):
    target_version_id: int
    expected_active_version_id: int | None


def _serialize_build(task: KnowledgeBuildTask, *, include_detail: bool = False, db=None):
    payload = {
        "id": task.id,
        "textbook_id": task.textbook_id,
        "target_version_id": task.target_version_id,
        "status": task.status,
        "stage": task.stage,
        "total_units": task.total_units,
        "completed_units": task.completed_units,
        "failed_units": task.failed_units,
        "lease_owner": task.lease_owner,
        "lease_expires_at": task.lease_expires_at,
        "retry_count": task.retry_count,
        "error_summary": task.error_summary,
        "build_config": task.build_config or {},
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }
    if include_detail and db is not None:
        units = (
            db.query(KnowledgeBuildUnit)
            .filter(KnowledgeBuildUnit.task_id == task.id)
            .order_by(KnowledgeBuildUnit.unit_type, KnowledgeBuildUnit.sequence)
            .all()
        )
        events = (
            db.query(KnowledgeBuildEvent)
            .filter(KnowledgeBuildEvent.task_id == task.id)
            .order_by(KnowledgeBuildEvent.id)
            .all()
        )
        payload["units"] = [
            {
                "id": row.id,
                "unit_type": row.unit_type,
                "sequence": row.sequence,
                "start_page": row.start_page,
                "end_page": row.end_page,
                "status": row.status,
                "attempts": row.attempts,
                "error_type": row.error_type,
                "error_detail": row.error_detail,
            }
            for row in units
        ]
        payload["events"] = [
            {
                "id": row.id,
                "level": row.level,
                "stage": row.stage,
                "message": row.message,
                "unit_id": row.unit_id,
                "created_at": row.created_at,
            }
            for row in events
        ]
    return payload


def _serialize_version(version: KnowledgeVersion, *, db: Session):
    points = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.version_id == version.id)
        .order_by(KnowledgePoint.id)
        .all()
    )
    chunks = (
        db.query(KnowledgeSourceChunk)
        .filter(KnowledgeSourceChunk.version_id == version.id)
        .order_by(KnowledgeSourceChunk.sequence)
        .all()
    )
    reviews = (
        db.query(KnowledgeReview)
        .filter(KnowledgeReview.version_id == version.id)
        .order_by(KnowledgeReview.id.desc())
        .all()
    )
    review_payload = []
    for review in reviews:
        items = (
            db.query(KnowledgeReviewItem)
            .filter(KnowledgeReviewItem.review_id == review.id)
            .order_by(KnowledgeReviewItem.id)
            .all()
        )
        review_payload.append(
            {
                "id": review.id,
                "reviewer_id": review.reviewer_id,
                "conclusion": review.conclusion,
                "note": review.note,
                "created_at": review.created_at,
                "items": [
                    {
                        "id": item.id,
                        "item_type": item.item_type,
                        "target_type": item.target_type,
                        "target_id": item.target_id,
                        "conclusion": item.conclusion,
                        "correction_note": item.correction_note,
                    }
                    for item in items
                ],
            }
        )
    return {
        "id": version.id,
        "textbook_id": version.textbook_id,
        "version_no": version.version_no,
        "parent_version_id": version.parent_version_id,
        "status": version.status,
        "point_count": version.point_count,
        "edge_count": version.edge_count,
        "source_chunk_count": version.source_chunk_count,
        "vector_count": version.vector_count,
        "reviewed_by": version.reviewed_by,
        "activated_by": version.activated_by,
        "created_at": version.created_at,
        "reviewed_at": version.reviewed_at,
        "activated_at": version.activated_at,
        "points": [
            {
                "id": point.id,
                "title": point.title,
                "chapter": point.chapter,
                "difficulty": point.difficulty,
                "source_chunk_id": point.source_chunk_id,
                "provenance_gap": point.provenance_gap,
            }
            for point in points
        ],
        "source_chunks": [
            {
                "id": chunk.id,
                "sequence": chunk.sequence,
                "start_page": chunk.start_page,
                "end_page": chunk.end_page,
                "parse_method": chunk.parse_method,
                "parser_version": chunk.parser_version,
            }
            for chunk in chunks
        ],
        "reviews": review_payload,
    }


def _raise_release_http(exc: Exception):
    if isinstance(exc, ReleaseNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ReleaseGateError):
        raise HTTPException(
            status_code=409,
            detail={"message": "版本未通过发布门禁", "issues": exc.issues},
        ) from exc
    raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/textbooks", status_code=201)
async def upload_textbook(
    response: Response,
    file: UploadFile = File(...),
    school_stage: str = Form(..., min_length=1, max_length=20),
    grade: str = Form(..., min_length=1, max_length=20),
    subject: str = Form(..., min_length=1, max_length=20),
    publisher: str = Form(..., min_length=1, max_length=100),
    edition: str = Form(..., min_length=1, max_length=100),
    volume: str = Form(..., min_length=1, max_length=50),
    source_note: str = Form(..., min_length=1),
    license_note: str = Form(..., min_length=1),
    source_url: str | None = Form(default=None, max_length=500),
    db: Session = Depends(get_db),
    admin_id: int = Depends(require_admin_user_id),
):
    metadata = {
        "school_stage": school_stage,
        "grade": grade,
        "subject": subject,
        "publisher": publisher,
        "edition": edition,
        "volume": volume,
        "source_note": source_note,
        "license_note": license_note,
        "source_url": source_url or "",
    }
    try:
        textbook, created = await store_textbook_upload(
            db, file, metadata=metadata, uploaded_by=admin_id
        )
    except TextbookValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TextbookConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response.status_code = 201 if created else 200
    return serialize_textbook(textbook, created=created)


@router.get("/textbooks")
def list_textbooks(
    db: Session = Depends(get_db),
    _admin_id: int = Depends(require_admin_user_id),
):
    rows = db.query(Textbook).order_by(Textbook.id.desc()).all()
    return {"items": [serialize_textbook(row) for row in rows], "total": len(rows)}


@router.get("/textbooks/{textbook_id}")
def textbook_detail(
    textbook_id: int,
    db: Session = Depends(get_db),
    _admin_id: int = Depends(require_admin_user_id),
):
    textbook = db.get(Textbook, textbook_id)
    if not textbook:
        raise HTTPException(status_code=404, detail="教材不存在")
    return serialize_textbook(textbook)


@router.post("/textbooks/{textbook_id}/builds", status_code=201)
def create_textbook_build(
    textbook_id: int,
    request: BuildCreateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=100),
    db: Session = Depends(get_db),
    admin_id: int = Depends(require_admin_user_id),
):
    if not db.get(Textbook, textbook_id):
        raise HTTPException(status_code=404, detail="教材不存在")
    task, created = create_build_task(
        db,
        textbook_id=textbook_id,
        requested_by=admin_id,
        idempotency_key=idempotency_key,
        build_config=request.model_dump(),
    )
    if task.textbook_id != textbook_id:
        raise HTTPException(status_code=409, detail="幂等键已用于其他教材")
    response.status_code = 201 if created else 200
    return _serialize_build(task)


@router.get("/builds")
def list_builds(
    db: Session = Depends(get_db),
    _admin_id: int = Depends(require_admin_user_id),
):
    rows = db.query(KnowledgeBuildTask).order_by(KnowledgeBuildTask.id.desc()).all()
    return {"items": [_serialize_build(row) for row in rows], "total": len(rows)}


@router.get("/builds/{task_id}")
def build_detail(
    task_id: int,
    db: Session = Depends(get_db),
    _admin_id: int = Depends(require_admin_user_id),
):
    task = db.get(KnowledgeBuildTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="构建任务不存在")
    return _serialize_build(task, include_detail=True, db=db)


@router.post("/builds/{task_id}/resume")
def resume_build(
    task_id: int,
    db: Session = Depends(get_db),
    _admin_id: int = Depends(require_admin_user_id),
):
    if not db.get(KnowledgeBuildTask, task_id):
        raise HTTPException(status_code=404, detail="构建任务不存在")
    try:
        task = resume_task(db, task_id, now=datetime.now())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_build(task)


@router.post("/builds/{task_id}/retry-failures")
def retry_build_failures(
    task_id: int,
    db: Session = Depends(get_db),
    _admin_id: int = Depends(require_admin_user_id),
):
    task = db.get(KnowledgeBuildTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="构建任务不存在")
    try:
        reset_failed_units(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_build(db.get(KnowledgeBuildTask, task_id))


@router.post("/builds/{task_id}/cancel")
def cancel_build(
    task_id: int,
    db: Session = Depends(get_db),
    _admin_id: int = Depends(require_admin_user_id),
):
    if not db.get(KnowledgeBuildTask, task_id):
        raise HTTPException(status_code=404, detail="构建任务不存在")
    try:
        task = cancel_task(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_build(task)


@router.get("/versions/{version_id}")
def version_detail(
    version_id: int,
    db: Session = Depends(get_db),
    _admin_id: int = Depends(require_admin_user_id),
):
    version = db.get(KnowledgeVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="知识版本不存在")
    return _serialize_version(version, db=db)


@router.post("/versions/{version_id}/reviews", status_code=201)
def review_version(
    version_id: int,
    request: ReviewRequest,
    db: Session = Depends(get_db),
    admin_id: int = Depends(require_admin_user_id),
):
    try:
        review = submit_review(
            db,
            version_id=version_id,
            reviewer_id=admin_id,
            conclusion=request.conclusion,
            note=request.note,
            items=[item.model_dump() for item in request.items],
        )
    except (ReleaseNotFoundError, ReleaseConflictError, ReleaseGateError) as exc:
        _raise_release_http(exc)
    return {
        "id": review.id,
        "version_id": review.version_id,
        "conclusion": review.conclusion,
        "note": review.note,
        "created_at": review.created_at,
    }


@router.post("/versions/{version_id}/activate")
def activate_knowledge_version(
    version_id: int,
    request: ActivateRequest,
    db: Session = Depends(get_db),
    admin_id: int = Depends(require_admin_user_id),
):
    try:
        version = activate_version(
            db,
            version_id=version_id,
            admin_id=admin_id,
            expected_active_version_id=request.expected_active_version_id,
        )
    except (ReleaseNotFoundError, ReleaseConflictError, ReleaseGateError) as exc:
        _raise_release_http(exc)
    return _serialize_version(version, db=db)


@router.post("/textbooks/{textbook_id}/rollback")
def rollback_knowledge_version(
    textbook_id: int,
    request: RollbackRequest,
    db: Session = Depends(get_db),
    admin_id: int = Depends(require_admin_user_id),
):
    try:
        version = rollback_textbook(
            db,
            textbook_id=textbook_id,
            target_version_id=request.target_version_id,
            admin_id=admin_id,
            expected_active_version_id=request.expected_active_version_id,
        )
    except (ReleaseNotFoundError, ReleaseConflictError, ReleaseGateError) as exc:
        _raise_release_http(exc)
    return _serialize_version(version, db=db)
