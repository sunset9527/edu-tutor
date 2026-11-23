"""add v18 final score reason

Revision ID: f3b7a9c2d614
Revises: e8b4a907c512
Create Date: 2026-11-23
"""

from alembic import op
import sqlalchemy as sa


revision = "f3b7a9c2d614"
down_revision = "e8b4a907c512"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("diagnostic_answers", sa.Column("final_score_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("diagnostic_answers", "final_score_reason")
