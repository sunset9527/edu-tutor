"""参数后台 API（v1.1）：GET/PUT 可配置参数"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings as app_settings
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

PARAM_KEYS = ["decay_lambda", "review_interval_base", "consolidation_threshold", "extract_min_confidence"]


class SettingsUpdate(BaseModel):
    decay_lambda: float | None = None
    review_interval_base: int | None = None
    consolidation_threshold: int | None = None
    extract_min_confidence: float | None = None


@router.get("")
def get_settings():
    """返回当前全部可配置参数"""
    return {
        "decay_lambda": settings_service.get_float("decay_lambda", app_settings.decay_lambda),
        "review_interval_base": settings_service.get_int("review_interval_base", app_settings.review_interval_base),
        "consolidation_threshold": settings_service.get_int("consolidation_threshold", app_settings.consolidation_threshold),
        "extract_min_confidence": settings_service.get_float("extract_min_confidence", 0.5),
    }


@router.put("")
def update_settings(payload: SettingsUpdate):
    """更新参数（立即生效）"""
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        settings_service.set_param(k, v)
    return get_settings()