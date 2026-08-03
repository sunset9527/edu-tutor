"""学生表 + 学生画像快照表"""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Student(Base):
    """学生表"""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="学生姓名")
    grade: Mapped[str] = mapped_column(String(20), nullable=False, comment="年级：初一/初二/初三…")
    subject: Mapped[str] = mapped_column(String(20), default="数学", comment="主科目")
    level: Mapped[str] = mapped_column(String(20), default="基础", comment="水平：入门/基础/中等/进阶")
    prefer_style: Mapped[str | None] = mapped_column(String(200), comment="学习偏好（讲解风格）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class StudentProfile(Base):
    """学生画像快照（由 semantic 记忆驱动更新，v0.2 启用）"""

    __tablename__ = "student_profile"

    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id"), primary_key=True
    )
    weaknesses: Mapped[list | None] = mapped_column(JSON, comment="薄弱点列表")
    strengths: Mapped[list | None] = mapped_column(JSON, comment="优势列表")
    wrong_stats: Mapped[dict | None] = mapped_column(JSON, comment="错题统计")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
