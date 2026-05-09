"""membership requests

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-05-09 00:00:00.000000

Adds:
  - communities.allow_membership_requests (boolean, default false)
  - membership_requests table
  - membership_request_status DB enum (pending / approved / denied)
  - four new audit_event_type values for membership request actions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "h2b3c4d5e6f7"
down_revision: Union[str, None] = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_membership_request_status = pg.ENUM(
    "pending", "approved", "denied", name="membership_request_status", create_type=False
)


def upgrade() -> None:
    op.add_column(
        "communities",
        sa.Column(
            "allow_membership_requests",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.execute("DROP TYPE IF EXISTS membership_request_status")
    op.execute(
        "CREATE TYPE membership_request_status AS ENUM ('pending', 'approved', 'denied')"
    )

    op.create_table(
        "membership_requests",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("community_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _membership_request_status,
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
        sa.ForeignKeyConstraint(["community_id"], ["communities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("community_id", "user_id", name="uq_membership_request_user"),
    )
    op.create_index(
        "ix_membership_requests_community_id", "membership_requests", ["community_id"]
    )
    op.create_index(
        "ix_membership_requests_user_id", "membership_requests", ["user_id"]
    )
    op.create_index(
        "ix_membership_requests_status", "membership_requests", ["status"]
    )

    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'community_settings_updated'"
    )
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'membership_request_submitted'"
    )
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'membership_request_approved'"
    )
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'membership_request_denied'"
    )


def downgrade() -> None:
    op.drop_index("ix_membership_requests_status", "membership_requests")
    op.drop_index("ix_membership_requests_user_id", "membership_requests")
    op.drop_index("ix_membership_requests_community_id", "membership_requests")
    op.drop_table("membership_requests")
    _membership_request_status.drop(op.get_bind(), checkfirst=True)
    op.drop_column("communities", "allow_membership_requests")
    # PostgreSQL does not support removing values from an enum type.
