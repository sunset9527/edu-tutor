"""v1.7 教材、构建、发布、证据与纠错模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Textbook(Base):
    __tablename__ = "textbooks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    identity_key: Mapped[str] = mapped_column(String(191), nullable=False, unique=True)
    school_stage: Mapped[str | None] = mapped_column(String(20))
    grade: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(20), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(100))
    edition: Mapped[str | None] = mapped_column(String(100))
    volume: Mapped[str | None] = mapped_column(String(50))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    page_count: Mapped[int | None] = mapped_column(Integer)
    file_sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_note: Mapped[str | None] = mapped_column(Text)
    license_note: Mapped[str | None] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    active_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_versions.id", use_alter=True, name="fk_textbooks_active_version"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_textbook_scope", "subject", "grade"),)


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    textbook_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("textbooks.id"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_versions.id")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="building")
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    activated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("textbook_id", "version_no", name="uk_knowledge_version_no"),
        Index("idx_knowledge_version_status", "status"),
    )


class KnowledgeBuildTask(Base):
    __tablename__ = "knowledge_build_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    textbook_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("textbooks.id"), nullable=False
    )
    target_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_versions.id")
    )
    requested_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    stage: Mapped[str | None] = mapped_column(String(30))
    total_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    build_config: Mapped[dict | None] = mapped_column(JSON)
    runtime_versions: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("idx_build_task_status", "status", "created_at"),)


class KnowledgeBuildUnit(Base):
    __tablename__ = "knowledge_build_units"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_build_tasks.id", ondelete="CASCADE"), nullable=False
    )
    unit_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_page: Mapped[int | None] = mapped_column(Integer)
    end_page: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    checkpoint: Mapped[dict | None] = mapped_column(JSON)
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("task_id", "unit_type", "sequence", name="uk_build_unit"),
        Index("idx_build_unit_status", "task_id", "status"),
    )


class KnowledgeBuildEvent(Base):
    __tablename__ = "knowledge_build_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_build_tasks.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_build_units.id", ondelete="SET NULL")
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    stage: Mapped[str | None] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KnowledgeSourceChunk(Base):
    __tablename__ = "knowledge_source_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_versions.id", ondelete="CASCADE"), nullable=False
    )
    build_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_build_units.id", ondelete="SET NULL")
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    region: Mapped[dict | None] = mapped_column(JSON)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parse_method: Mapped[str] = mapped_column(String(30), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("version_id", "sequence", name="uk_source_chunk_sequence"),
    )


class KnowledgeReview(Base):
    __tablename__ = "knowledge_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_versions.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    conclusion: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KnowledgeReviewItem(Base):
    __tablename__ = "knowledge_review_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("knowledge_reviews.id", ondelete="CASCADE"), nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    original_value: Mapped[dict | None] = mapped_column(JSON)
    conclusion: Mapped[str] = mapped_column(String(20), nullable=False)
    correction_note: Mapped[str | None] = mapped_column(Text)


class AnswerEvidenceLedger(Base):
    __tablename__ = "answer_evidence_ledgers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    assistant_message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    knowledge_evidence: Mapped[list | None] = mapped_column(JSON)
    memory_evidence: Mapped[list | None] = mapped_column(JSON)
    retrieval_config: Mapped[dict | None] = mapped_column(JSON)
    evidence_gap: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CorrectionTicket(Base):
    __tablename__ = "correction_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_value: Mapped[dict] = mapped_column(JSON, nullable=False)
    proposed_value: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    submitted_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    handled_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    handling_note: Mapped[str | None] = mapped_column(Text)
    applied_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("knowledge_versions.id")
    )
    result_reference: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    handled_at: Mapped[datetime | None] = mapped_column(DateTime)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("idx_correction_status", "status", "category"),)
