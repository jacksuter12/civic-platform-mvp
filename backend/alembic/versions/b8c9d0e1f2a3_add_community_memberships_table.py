"""add community memberships table

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-04-12 00:01:00.000000

Adds:
  - community_memberships table
  - Reuses the existing user_tier ENUM for the tier column
  - UNIQUE(community_id, user_id) — one membership record per user per community
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS community_memberships (
            id              UUID        NOT NULL DEFAULT gen_random_uuid(),
            community_id    UUID        NOT NULL REFERENCES communities(id),
            user_id         UUID        NOT NULL REFERENCES users(id),
            tier            user_tier   NOT NULL DEFAULT 'REGISTERED',
            joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            verified_at     TIMESTAMPTZ NULL,
            verified_by_id  UUID        REFERENCES users(id),
            is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            CONSTRAINT uq_community_membership_user UNIQUE (community_id, user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_community_memberships_community_id
        ON community_memberships (community_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_community_memberships_user_id
        ON community_memberships (user_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_community_memberships_user_id")
    op.execute("DROP INDEX IF EXISTS ix_community_memberships_community_id")
    op.execute("DROP TABLE IF EXISTS community_memberships")
