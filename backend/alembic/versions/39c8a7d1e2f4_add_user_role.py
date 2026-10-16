"""add user role

Revision ID: 39c8a7d1e2f4
Revises: 7c1e6a9d4b20
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "39c8a7d1e2f4"
down_revision: str | None = "7c1e6a9d4b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
