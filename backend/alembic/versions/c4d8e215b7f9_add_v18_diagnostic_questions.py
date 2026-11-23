"""add v18 diagnostic questions

Revision ID: c4d8e215b7f9
Revises: 7efb3126a01c
Create Date: 2026-11-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d8e215b7f9"
down_revision: Union[str, None] = "7efb3126a01c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("knowledge_version_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_point_id", sa.BigInteger(), nullable=False),
        sa.Column("source_chunk_id", sa.BigInteger(), nullable=False),
        sa.Column("question_type", sa.String(length=20), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("answer_key_json", sa.JSON(), nullable=True),
        sa.Column("rubric_json", sa.JSON(), nullable=True),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_version_id"], ["knowledge_versions.id"]),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"]),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["knowledge_source_chunks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_diagnostic_question_scope", "diagnostic_questions", ["knowledge_version_id", "knowledge_point_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_table("diagnostic_questions")
