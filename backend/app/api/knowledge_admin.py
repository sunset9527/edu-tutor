"""v1.7 教材与知识版本治理管理员接口。"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.auth import require_admin_user_id
from app.core.database import get_db
from app.models.knowledge_governance import Textbook
from app.services.knowledge.textbook_service import (
    TextbookConflictError,
    TextbookValidationError,
    serialize_textbook,
    store_textbook_upload,
)


router = APIRouter(prefix="/api/admin", tags=["knowledge-admin"])


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
