"""export status (MP4 com sobreposição)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13 23:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("export_status", sa.String(length=20), server_default="idle", nullable=False),
    )
    op.add_column("videos", sa.Column("export_progress", sa.Float(), nullable=True))
    op.add_column("videos", sa.Column("export_error", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "exported_at")
    op.drop_column("videos", "export_error")
    op.drop_column("videos", "export_progress")
    op.drop_column("videos", "export_status")
