"""系统参数服务：DB 存储 + 内存缓存（PUT 后即时生效）"""
import logging

from app.core.database import SessionLocal
from app.models.setting import SystemSetting

logger = logging.getLogger(__name__)

_param_cache: dict[str, str] = {}

# 可配置参数及默认值（来自 config）
PARAM_DEFAULTS = {
    "decay_lambda": None,            # 运行时从 settings.decay_lambda 取
    "review_interval_base": None,
    "consolidation_threshold": None,
    "extract_min_confidence": None,
}


def get_param(key: str, default):
    """读取参数（缓存优先，DB 次之，默认兜底）"""
    if key in _param_cache:
        return _param_cache[key]
    db = SessionLocal()
    try:
        row = db.get(SystemSetting, key)
        val = row.value if row else default
    finally:
        db.close()
    if val is not None:
        _param_cache[key] = str(val)
    return val


def set_param(key: str, value) -> None:
    db = SessionLocal()
    try:
        row = db.get(SystemSetting, key)
        if row:
            row.value = str(value)
        else:
            db.add(SystemSetting(key=key, value=str(value)))
        db.commit()
        _param_cache[key] = str(value)
        logger.info(f"参数更新: {key}={value}")
    finally:
        db.close()


def get_float(key: str, default: float) -> float:
    try:
        return float(get_param(key, default))
    except (TypeError, ValueError):
        return default


def get_int(key: str, default: int) -> int:
    try:
        return int(float(get_param(key, default)))
    except (TypeError, ValueError):
        return default