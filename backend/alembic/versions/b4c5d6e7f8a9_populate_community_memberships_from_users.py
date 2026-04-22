"""populate community memberships from users

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-04-12 00:07:00.000000

Data migration: inserts one community_memberships row per existing user, copying
their current global tier and is_active status, into the test/legacy community.
joined_at is set to the user's created_at so the membership timestamp is
historically accurate.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO community_memberships
            (community_id, user_id, tier, joined_at, is_active)
        SELECT
            (SELECT id FROM communities WHERE slug = 'test'),
            id,
            tier,
            created_at,
            is_active
        FROM users
    """)


def downgrade() -> None:
    # Remove memberships for the test community only; leaves other communities intact
    op.execute("""
        DELETE FROM community_memberships
        WHERE community_id = (SELECT id FROM communities WHERE slug = 'test')
    """)
