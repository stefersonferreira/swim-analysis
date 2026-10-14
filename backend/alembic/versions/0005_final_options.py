"""final video options: partial strokes and reviewer notes

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("strokes_partial", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("videos", sa.Column("review_notes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "review_notes")
    op.drop_column("videos", "strokes_partial")
