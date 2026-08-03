"""知识点表 + 图谱边表 + 错题本（知识引擎，v0.3 启用，v0.1 先建表）"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KnowledgePoint(Base):
    """知识点表（LLM Wiki 编译落库）"""

    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(20), nullable=False)
    grade: Mapped[str | None] = mapped_column(String(20))
    chapter: Mapped[str | None] = mapped_column(String(100), comment="所属章节")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    content_md: Mapped[str | None] = mapped_column(Text, comment="知识点页面正文")
    difficulty: Mapped[str] = mapped_column(String(20), default="基础", comment="基础/进阶/拔高")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_kp_subject", "subject", "grade"),)


class KnowledgePointLink(Base):
    """知识点图谱边表（wikilinks 落库）"""

    __tablename__ = "knowledge_point_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_kp_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_points.id"), nullable=False
    )
    target_kp_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_points.id"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(
        String(20), default="related", comment="prerequisite/related/example/contradicts"
    )

    __table_args__ = (
        UniqueConstraint("source_kp_id", "target_kp_id", "link_type", name="uk_link"),
    )


class WrongQuestion(Base):
    """错题本"""

    __tablename__ = "wrong_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id"), nullable=False
    )
    knowledge_point_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_points.id")
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    analysis: Mapped[str | None] = mapped_column(Text, comment="错误原因分析（LLM 生成）")
    error_type: Mapped[str | None] = mapped_column(String(50), comment="概念不清/计算错误/审题失误…")
    mastered: Mapped[int] = mapped_column(default=0, comment="0=未掌握 1=已掌握")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_wq_student", "student_id", "mastered"),)
