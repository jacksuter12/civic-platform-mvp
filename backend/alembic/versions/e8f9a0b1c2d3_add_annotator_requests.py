"""add annotator requests

Revision ID: e8f9a0b1c2d3
Revises: d6e7f8a9b0c1
Create Date: 2026-05-03 00:00:00.000000

Adds:
  - annotator_requests table
  - annotator_request_status DB enum (pending / approved / denied)
  - three new audit_event_type values for annotator request actions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_annotator_request_status = pg.ENUM(
    "pending", "approved", "denied", name="annotator_request_status", create_type=False
)


def upgrade() -> None:
    # Drop orphaned enum type if a previous partial run left it behind, then re-create clean
    op.execute("DROP TYPE IF EXISTS annotator_request_status")
    op.execute("CREATE TYPE annotator_request_status AS ENUM ('pending', 'approved', 'denied')")

    op.create_table(
        "annotator_requests",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _annotator_request_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_annotator_requests_user_id", "annotator_requests", ["user_id"])
    op.create_index("ix_annotator_requests_status", "annotator_requests", ["status"])

    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'annotator_request_submitted'"
    )
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'annotator_request_approved'"
    )
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'annotator_request_denied'"
    )


def downgrade() -> None:
    op.drop_index("ix_annotator_requests_status", "annotator_requests")
    op.drop_index("ix_annotator_requests_user_id", "annotator_requests")
    op.drop_table("annotator_requests")
    _annotator_request_status.drop(op.get_bind(), checkfirst=True)
    # PostgreSQL does not support removing values from an enum type.
