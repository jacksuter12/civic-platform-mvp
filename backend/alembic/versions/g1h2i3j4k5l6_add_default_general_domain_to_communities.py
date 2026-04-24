"""add default general domain to communities

Revision ID: g1h2i3j4k5l6
Revises: d6e7f8a9b0c1
Create Date: 2026-04-24 00:00:00.000000
"""

from alembic import op

revision = "g1h2i3j4k5l6"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Activate any inactive general domain for communities with no active domains.
    op.execute("""
        UPDATE domains d
        SET is_active = TRUE,
            updated_at = now()
        FROM communities c
        WHERE d.community_id = c.id
          AND c.is_active = TRUE
          AND d.slug = 'general'
          AND d.is_active = FALSE
          AND NOT EXISTS (
              SELECT 1 FROM domains d2
              WHERE d2.community_id = c.id
                AND d2.is_active = TRUE
          )
    """)

    # Add a default active general domain for communities with no active domains.
    op.execute("""
        INSERT INTO domains (id, community_id, slug, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'general', 'General',
               'Default discussion domain for this community.', TRUE
        FROM communities c
        WHERE c.is_active = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM domains d
              WHERE d.community_id = c.id
                AND d.is_active = TRUE
          )
          AND NOT EXISTS (
              SELECT 1 FROM domains d
              WHERE d.community_id = c.id
                AND d.slug = 'general'
          )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM domains d
        USING communities c
        WHERE d.community_id = c.id
          AND c.is_active = TRUE
          AND d.slug = 'general'
          AND d.name = 'General'
          AND d.description = 'Default discussion domain for this community.'
    """)
