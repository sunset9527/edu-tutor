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
    Textbook,
)
from app.services.knowledge.build_repository import (
    cancel_task,
    create_build_task,
    reset_failed_units,
    resume_task,
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
