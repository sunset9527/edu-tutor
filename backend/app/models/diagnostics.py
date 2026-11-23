"""v1.8 诊断题、会话与作答领域模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DiagnosticQuestion(Base):
    __tablename__ = "diagnostic_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_versions.id"), nullable=False)
    knowledge_point_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_points.id"), nullable=False)
    source_chunk_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_source_chunks.id"), nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[list | None] = mapped_column(JSON)
    answer_key_json: Mapped[dict | None] = mapped_column(JSON)
    rubric_json: Mapped[dict | None] = mapped_column(JSON)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DiagnosticSession(Base):
    __tablename__ = "diagnostic_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    goal_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("learning_goals.id"), nullable=False)
    goal_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("learning_goal_versions.id"), nullable=False)
    knowledge_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_versions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)


class DiagnosticAnswer(Base):
    __tablename__ = "diagnostic_answers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("diagnostic_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("diagnostic_questions.id"), nullable=False)
    raw_answer: Mapped[dict | None] = mapped_column(JSON)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[int | None] = mapped_column(Integer)
    deterministic_score: Mapped[int | None] = mapped_column(Integer)
    grading_basis: Mapped[dict | None] = mapped_column(JSON)
    suggested_score: Mapped[int | None] = mapped_column(Integer)
    suggestion_basis: Mapped[dict | None] = mapped_column(JSON)
    final_score: Mapped[int | None] = mapped_column(Integer)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DiagnosticKnowledgeResult(Base):
    __tablename__ = "diagnostic_knowledge_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("diagnostic_sessions.id", ondelete="CASCADE"), nullable=False)
    knowledge_point_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_points.id"), nullable=False)
    score_rate: Mapped[float | None] = mapped_column(nullable=True)
    valid_answer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mastery: Mapped[str | None] = mapped_column(String(20))
    evidence_status: Mapped[str] = mapped_column(String(20), nullable=False, default="no_evidence")
    evidence_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
