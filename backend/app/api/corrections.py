"""登录用户纠错反馈接口。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import require_current_user_id
from app.core.database import get_db
from app.services.knowledge.correction_service import (
    CorrectionConflictError,
    CorrectionNotFoundError,
    create_ticket,
    serialize_ticket,
)


router = APIRouter(prefix="/api/corrections", tags=["corrections"])


class CorrectionCreateRequest(BaseModel):
    assistant_message_id: int
    category: str = Field(pattern="^(knowledge|question|explanation|memory)$")
    target_id: int | None = None
    proposed_value: dict | None = None
    reason: str = Field(min_length=1, max_length=4000)


@router.post("", status_code=201)
def submit_correction(
    request: CorrectionCreateRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    try:
        ticket = create_ticket(
            db,
            submitted_by=user_id,
            category=request.category,
            assistant_message_id=request.assistant_message_id,
            proposed_value=request.proposed_value,
            reason=request.reason,
            target_id=request.target_id,
        )
    except CorrectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CorrectionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return serialize_ticket(ticket)
