"""add learning events

Revision ID: 7c1e6a9d4b20
Revises: fdf80382569e
Create Date: 2026-10-12 11:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1e6a9d4b20"
down_revision: Union[str, None] = "fdf80382569e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=True),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("knowledge_point_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["knowledge_points.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_learning_events_student_time",
        "learning_events",
        ["student_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "idx_learning_events_type",
        "learning_events",
        ["student_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    # MySQL uses the student/time index for the student foreign key; dropping
    # the table removes both indexes without violating that dependency.
    op.drop_table("learning_events")
