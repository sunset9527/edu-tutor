"""add AI diagnostic question review audit

Revision ID: b6e2c8f4a913
Revises: a9d1f3e5b726
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa


revision = "b6e2c8f4a913"
down_revision = "a9d1f3e5b726"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("diagnostic_questions", sa.Column("review_mode", sa.String(length=30), nullable=True))
    op.add_column("diagnostic_questions", sa.Column("ai_model", sa.String(length=100), nullable=True))
    op.add_column("diagnostic_questions", sa.Column("ai_review_json", sa.JSON(), nullable=True))
    op.add_column("diagnostic_questions", sa.Column("ai_reviewed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("diagnostic_questions", "ai_reviewed_at")
    op.drop_column("diagnostic_questions", "ai_review_json")
    op.drop_column("diagnostic_questions", "ai_model")
    op.drop_column("diagnostic_questions", "review_mode")
