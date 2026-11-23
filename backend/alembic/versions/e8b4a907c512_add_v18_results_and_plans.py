"""add v18 diagnostic results and plans

Revision ID: e8b4a907c512
Revises: d6a1f9c8e203
Create Date: 2026-11-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e8b4a907c512"
down_revision: Union[str, None] = "d6a1f9c8e203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table("diagnostic_knowledge_results", sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False), sa.Column("session_id", sa.BigInteger(), nullable=False), sa.Column("knowledge_point_id", sa.BigInteger(), nullable=False), sa.Column("score_rate", sa.Float(), nullable=True), sa.Column("valid_answer_count", sa.Integer(), nullable=False), sa.Column("mastery", sa.String(length=20), nullable=True), sa.Column("evidence_status", sa.String(length=20), nullable=False), sa.Column("evidence_json", sa.JSON(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False), sa.ForeignKeyConstraint(["session_id"], ["diagnostic_sessions.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("session_id", "knowledge_point_id", name="uk_diagnostic_kp_result"))
    op.create_table("learning_plan_versions", sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False), sa.Column("student_id", sa.BigInteger(), nullable=False), sa.Column("goal_id", sa.BigInteger(), nullable=False), sa.Column("goal_version_id", sa.BigInteger(), nullable=False), sa.Column("diagnostic_session_id", sa.BigInteger(), nullable=True), sa.Column("knowledge_version_id", sa.BigInteger(), nullable=False), sa.Column("status", sa.String(length=20), nullable=False), sa.Column("adjustment_reason", sa.String(length=50), nullable=False), sa.Column("total_available_minutes", sa.Integer(), nullable=False), sa.Column("scheduled_minutes", sa.Integer(), nullable=False), sa.Column("missing_minutes", sa.Integer(), nullable=False), sa.Column("evidence_snapshot", sa.JSON(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False), sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["goal_id"], ["learning_goals.id"]), sa.ForeignKeyConstraint(["goal_version_id"], ["learning_goal_versions.id"]), sa.ForeignKeyConstraint(["diagnostic_session_id"], ["diagnostic_sessions.id"]), sa.ForeignKeyConstraint(["knowledge_version_id"], ["knowledge_versions.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_table("learning_plan_items", sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False), sa.Column("plan_version_id", sa.BigInteger(), nullable=False), sa.Column("week_no", sa.Integer(), nullable=True), sa.Column("sequence_no", sa.Integer(), nullable=False), sa.Column("knowledge_point_id", sa.BigInteger(), nullable=False), sa.Column("estimated_minutes", sa.Integer(), nullable=False), sa.Column("recommendation_reasons", sa.JSON(), nullable=True), sa.Column("completion_condition", sa.Text(), nullable=False), sa.Column("evidence_json", sa.JSON(), nullable=True), sa.Column("scheduled", sa.Boolean(), nullable=False), sa.ForeignKeyConstraint(["plan_version_id"], ["learning_plan_versions.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"]), sa.PrimaryKeyConstraint("id"))

def downgrade() -> None:
    op.drop_table("learning_plan_items")
    op.drop_table("learning_plan_versions")
    op.drop_table("diagnostic_knowledge_results")
