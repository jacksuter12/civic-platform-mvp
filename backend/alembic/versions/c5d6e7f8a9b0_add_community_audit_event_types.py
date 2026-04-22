"""add community audit event types

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-04-12 00:08:00.000000

Adds three new values to the audit_event_type ENUM:
  COMMUNITY_CREATED, COMMUNITY_MEMBER_JOINED, COMMUNITY_MEMBER_PROMOTED

Note: PostgreSQL does not support removing enum values, so downgrade cannot
reverse these additions. This matches the convention in all prior migrations.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for event in (
        "COMMUNITY_CREATED",
        "COMMUNITY_MEMBER_JOINED",
        "COMMUNITY_MEMBER_PROMOTED",
    ):
        op.execute(
            f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{event}'"
        )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; entries remain on downgrade.
    pass
