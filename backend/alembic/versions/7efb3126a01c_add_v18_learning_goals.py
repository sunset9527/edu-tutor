"""add v18 learning goals

Revision ID: 7efb3126a01c
Revises: 31b933ce603d
Create Date: 2026-11-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7efb3126a01c"
down_revision: Union[str, None] = "31b933ce603d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_goals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.BigInteger(), nullable=False),
        sa.Column("current_version_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "learning_goal_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("goal_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("knowledge_version_id", sa.BigInteger(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("weekly_minutes", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=20), nullable=False),
        sa.Column("target_level", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("change_reason", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["learning_goals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_version_id"], ["knowledge_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("goal_id", "version_no", name="uk_learning_goal_version_no"),
    )
    op.create_foreign_key(
        "fk_learning_goals_current_version",
        "learning_goals",
        "learning_goal_versions",
        ["current_version_id"],
        ["id"],
    )
    op.create_index(
        "idx_learning_goal_student", "learning_goals", ["student_id", "current_version_id"], unique=False
    )
    op.create_index(
        "idx_goal_version_knowledge", "learning_goal_versions", ["knowledge_version_id", "status"], unique=False
    )
    op.create_table(
        "learning_goal_targets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("goal_version_id", sa.BigInteger(), nullable=False),
        sa.Column("knowledge_point_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["goal_version_id"], ["learning_goal_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("goal_version_id", "knowledge_point_id", name="uk_goal_target"),
    )


def downgrade() -> None:
    op.drop_table("learning_goal_targets")
    op.drop_index("idx_goal_version_knowledge", table_name="learning_goal_versions")
    op.drop_constraint("fk_learning_goals_current_version", "learning_goals", type_="foreignkey")
    op.drop_table("learning_goal_versions")
    op.drop_index("idx_learning_goal_student", table_name="learning_goals")
    op.drop_table("learning_goals")
