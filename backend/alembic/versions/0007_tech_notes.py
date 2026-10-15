"""technique notes per key frame

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-14 23:50:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("tech_notes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "tech_notes")
