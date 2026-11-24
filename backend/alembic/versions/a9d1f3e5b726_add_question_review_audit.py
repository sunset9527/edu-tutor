"""add diagnostic question review audit and immutability trigger

Revision ID: a9d1f3e5b726
Revises: f3b7a9c2d614
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa


revision = "a9d1f3e5b726"
down_revision = "f3b7a9c2d614"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("diagnostic_questions", sa.Column("reviewed_by", sa.String(length=100), nullable=True))
    op.add_column("diagnostic_questions", sa.Column("review_note", sa.Text(), nullable=True))
    op.execute("""
        CREATE TRIGGER trg_diagnostic_questions_published_immutable
        BEFORE UPDATE ON diagnostic_questions
        FOR EACH ROW
        BEGIN
            IF OLD.status = 'published' THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'published diagnostic question is immutable';
            END IF;
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_diagnostic_questions_published_immutable")
    op.drop_column("diagnostic_questions", "review_note")
    op.drop_column("diagnostic_questions", "reviewed_by")
