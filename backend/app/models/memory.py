"""长期记忆主表 + 冲突记录 + 复习计划（v0.2 启用核心逻辑，v0.1 先建表）"""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Memory(Base):
    """长期记忆主表"""

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id"), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="semantic/episodic/procedural"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="记忆内容（可读文本）")
    structured_data: Mapped[dict | None] = mapped_column(JSON, comment="三元组/画像字段")
    source_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sessions.id"), comment="溯源"
    )
    knowledge_point_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_points.id"), comment="关联知识点（双引擎桥梁）"
    )
    confidence: Mapped[float] = mapped_column(default=0.7, comment="置信度 0~1")
    strength: Mapped[float] = mapped_column(default=0.6, comment="记忆强度（遗忘曲线）")
    mastery: Mapped[str] = mapped_column(
        String(20), default="不懂", comment="掌握度：不懂/基本会/熟练/精通"
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(
        String(20), default="active", comment="active/stale/contradicted/archived"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_memories_student", "student_id", "memory_type", "status"),)


class MemoryConflict(Base):
    """记忆冲突记录"""

    __tablename__ = "memory_conflicts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id"), nullable=False
    )
    old_memory_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("memories.id"), nullable=False
    )
    new_content: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[str] = mapped_column(String(20), default="keep_new", comment="keep_new/mark_doubt")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReviewPlan(Base):
    """复习计划（遗忘曲线调度，v0.3 启用）"""

    __tablename__ = "review_plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="memory/knowledge_point"
    )
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interval_days: Mapped[int] = mapped_column(default=1)
    next_review_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="pending/done/skipped")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_rp_student", "student_id", "status", "next_review_at"),)
