"""SQLAlchemy 模型统一导出（alembic autogenerate 依赖此文件）"""
from app.models.student import Student, StudentProfile
from app.models.user import User
from app.models.session import Session, Message
from app.models.memory import Memory, MemoryConflict, ReviewPlan
from app.models.knowledge import KnowledgePoint, KnowledgePointLink, WrongQuestion
from app.models.setting import SystemSetting

__all__ = [
    "Student",
    "StudentProfile",
    "User",
    "Session",
    "Message",
    "Memory",
    "MemoryConflict",
    "ReviewPlan",
    "KnowledgePoint",
    "KnowledgePointLink",
    "WrongQuestion",
    "SystemSetting",
]
