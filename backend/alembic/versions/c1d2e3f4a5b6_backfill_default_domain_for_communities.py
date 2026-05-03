"""Backfill default General domain for communities without any domain

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a0
Create Date: 2026-05-03

"""
from typing import Union

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b1c2d3e4f5a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO domains (id, community_id, slug, name, description, is_active)
        SELECT
            gen_random_uuid(),
            c.id,
            'general',
            'General',
            'General discussion',
            true
        FROM communities c
        WHERE NOT EXISTS (
            SELECT 1 FROM domains d WHERE d.community_id = c.id
        )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM domains
        WHERE slug = 'general'
          AND name = 'General'
          AND description = 'General discussion'
    """)
