"""v1.7 教材治理数据模型契约。"""

import app.models  # noqa: F401
from sqlalchemy import inspect

from app.core.database import Base, engine
from app.models.knowledge import KnowledgePoint


def test_governance_tables_are_registered_in_metadata():
    expected = {
        "textbooks",
        "knowledge_versions",
        "knowledge_source_chunks",
        "knowledge_build_tasks",
        "knowledge_build_units",
        "knowledge_build_events",
        "knowledge_reviews",
        "knowledge_review_items",
        "answer_evidence_ledgers",
        "correction_tickets",
    }
    assert expected <= set(Base.metadata.tables)


def test_knowledge_point_exposes_versioned_provenance_columns():
    columns = set(KnowledgePoint.__table__.columns.keys())
    assert {"version_id", "source_chunk_id", "source_excerpt", "provenance_gap"} <= columns


def test_database_schema_contains_governance_tables_and_columns():
    inspector = inspect(engine)
    assert {
        "textbooks",
        "knowledge_versions",
        "knowledge_build_tasks",
        "answer_evidence_ledgers",
        "correction_tickets",
    } <= set(inspector.get_table_names())
    knowledge_columns = {row["name"] for row in inspector.get_columns("knowledge_points")}
    assert {"version_id", "source_chunk_id", "source_excerpt", "provenance_gap"} <= knowledge_columns
