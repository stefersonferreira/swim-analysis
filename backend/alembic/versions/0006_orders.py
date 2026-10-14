"""orders: customer, deadline, delivery link, coach feedback

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14 22:30:00
"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add = op.add_column
    add("videos", sa.Column("origin", sa.String(10), server_default="coach", nullable=False))
    add("videos", sa.Column("customer_name", sa.String(200), nullable=True))
    add("videos", sa.Column("customer_email", sa.String(200), nullable=True))
    add("videos", sa.Column("customer_phone", sa.String(40), nullable=True))
    add("videos", sa.Column("customer_notes", sa.Text(), nullable=True))
    add("videos", sa.Column("order_status", sa.String(20), server_default="new", nullable=False))
    add("videos", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    add("videos", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    add("videos", sa.Column("paid", sa.Boolean(), server_default="false", nullable=False))
    add("videos", sa.Column("share_token", sa.String(40), nullable=True))
    add("videos", sa.Column("feedback", sa.JSON(), nullable=True))
    # vídeos que já existem ganham um link próprio
    conn = op.get_bind()
    ids = [r[0] for r in conn.execute(sa.text("select id from videos"))]
    for vid in ids:
        conn.execute(
            sa.text("update videos set share_token = :t where id = :i"),
            {"t": secrets.token_urlsafe(16), "i": vid},
        )
    op.alter_column("videos", "share_token", nullable=False)
    op.create_index("ix_videos_share_token", "videos", ["share_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_videos_share_token", table_name="videos")
    for c in (
        "feedback", "share_token", "paid", "delivered_at", "due_at", "order_status",
        "customer_notes", "customer_phone", "customer_email", "customer_name", "origin",
    ):  # fmt: skip
        op.drop_column("videos", c)
