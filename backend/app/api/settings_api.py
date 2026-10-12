"""参数后台 API（v1.1）：GET/PUT 可配置参数"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings as app_settings
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

PARAM_KEYS = [
    "decay_lambda",
    "review_interval_base",
    "consolidation_threshold",
    "extract_min_confidence",
    "retrieval_weight_similarity",
    "retrieval_weight_recency",
    "retrieval_weight_retention",
    "retrieval_weight_confidence",
    "retrieval_recency_days",
    "retrieval_profile_quota",
    "retrieval_relevant_quota",
    "retrieval_recent_quota",
]


class SettingsUpdate(BaseModel):
    decay_lambda: float | None = None
    review_interval_base: int | None = None
    consolidation_threshold: int | None = None
    extract_min_confidence: float | None = None
    retrieval_weight_similarity: float | None = None
    retrieval_weight_recency: float | None = None
    retrieval_weight_retention: float | None = None
    retrieval_weight_confidence: float | None = None
    retrieval_recency_days: float | None = None
    retrieval_profile_quota: int | None = None
    retrieval_relevant_quota: int | None = None
    retrieval_recent_quota: int | None = None


@router.get("")
def get_settings():
    """返回当前全部可配置参数"""
    return {
        "decay_lambda": settings_service.get_float("decay_lambda", app_settings.decay_lambda),
        "review_interval_base": settings_service.get_int("review_interval_base", app_settings.review_interval_base),
        "consolidation_threshold": settings_service.get_int("consolidation_threshold", app_settings.consolidation_threshold),
        "extract_min_confidence": settings_service.get_float("extract_min_confidence", 0.5),
        "retrieval_weight_similarity": settings_service.get_float(
            "retrieval_weight_similarity", app_settings.retrieval_weight_similarity
        ),
        "retrieval_weight_recency": settings_service.get_float(
            "retrieval_weight_recency", app_settings.retrieval_weight_recency
        ),
        "retrieval_weight_retention": settings_service.get_float(
            "retrieval_weight_retention", app_settings.retrieval_weight_retention
        ),
        "retrieval_weight_confidence": settings_service.get_float(
            "retrieval_weight_confidence", app_settings.retrieval_weight_confidence
        ),
        "retrieval_recency_days": settings_service.get_float(
            "retrieval_recency_days", app_settings.retrieval_recency_days
        ),
        "retrieval_profile_quota": settings_service.get_int(
            "retrieval_profile_quota", app_settings.retrieval_profile_quota
        ),
        "retrieval_relevant_quota": settings_service.get_int(
            "retrieval_relevant_quota", app_settings.retrieval_relevant_quota
        ),
        "retrieval_recent_quota": settings_service.get_int(
            "retrieval_recent_quota", app_settings.retrieval_recent_quota
        ),
    }


@router.put("")
def update_settings(payload: SettingsUpdate):
    """更新参数（立即生效）"""
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        settings_service.set_param(k, v)
    return get_settings()
