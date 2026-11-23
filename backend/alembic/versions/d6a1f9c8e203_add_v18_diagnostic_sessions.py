"""add v18 diagnostic sessions

Revision ID: d6a1f9c8e203
Revises: c4d8e215b7f9
Create Date: 2026-11-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d6a1f9c8e203"
down_revision: Union[str, None] = "c4d8e215b7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table("diagnostic_sessions", sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False), sa.Column("student_id", sa.BigInteger(), nullable=False), sa.Column("goal_id", sa.BigInteger(), nullable=False), sa.Column("goal_version_id", sa.BigInteger(), nullable=False), sa.Column("knowledge_version_id", sa.BigInteger(), nullable=False), sa.Column("status", sa.String(length=20), nullable=False), sa.Column("started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False), sa.Column("submitted_at", sa.DateTime(), nullable=True), sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["goal_id"], ["learning_goals.id"]), sa.ForeignKeyConstraint(["goal_version_id"], ["learning_goal_versions.id"]), sa.ForeignKeyConstraint(["knowledge_version_id"], ["knowledge_versions.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_table("diagnostic_answers", sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False), sa.Column("session_id", sa.BigInteger(), nullable=False), sa.Column("question_id", sa.BigInteger(), nullable=False), sa.Column("raw_answer", sa.JSON(), nullable=True), sa.Column("elapsed_seconds", sa.Integer(), nullable=True), sa.Column("confidence", sa.Integer(), nullable=True), sa.Column("deterministic_score", sa.Integer(), nullable=True), sa.Column("grading_basis", sa.JSON(), nullable=True), sa.Column("suggested_score", sa.Integer(), nullable=True), sa.Column("suggestion_basis", sa.JSON(), nullable=True), sa.Column("final_score", sa.Integer(), nullable=True), sa.Column("confirmed_at", sa.DateTime(), nullable=True), sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False), sa.ForeignKeyConstraint(["session_id"], ["diagnostic_sessions.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["question_id"], ["diagnostic_questions.id"]), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("session_id", "question_id", name="uk_diagnostic_answer"))

def downgrade() -> None:
    op.drop_table("diagnostic_answers")
    op.drop_table("diagnostic_sessions")
