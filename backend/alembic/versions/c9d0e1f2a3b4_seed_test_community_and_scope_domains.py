"""seed test community and scope domains

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-04-12 00:02:00.000000

Single transaction:
  1. INSERT the 'test' community (all legacy data home)
  2. ADD community_id NULL to domains
  3. BACKFILL domains.community_id from the test community
  4. SET NOT NULL
  5. DROP the old global unique index on domains.slug
  6. ADD UNIQUE(community_id, slug) — slug is unique within a community, not globally
  7. ADD FK domains.community_id → communities.id
  8. ADD INDEX on domains.community_id
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Insert the test/legacy community.
    #    created_by_id is NULL — this is seed data with no human creator.
    op.execute("""
        INSERT INTO communities (
            slug, name, description, community_type,
            boundary_desc, verification_method,
            is_public, is_invite_only, is_active, created_by_id
        ) VALUES (
            'test',
            'Test / Legacy',
            'Pre-community-era threads and seed data. Used for ongoing testing.',
            'INSTITUTIONAL',
            'Legacy platform members and ongoing test data',
            'Email magic link (legacy global tier, no scoped verification)',
            TRUE, FALSE, TRUE, NULL
        )
    """)

    # 2. Add community_id column (nullable for backfill)
    op.execute("ALTER TABLE domains ADD COLUMN community_id UUID NULL")

    # 3. Backfill all existing domains → test community
    op.execute("""
        UPDATE domains
        SET community_id = (SELECT id FROM communities WHERE slug = 'test')
    """)

    # 4. Enforce NOT NULL now that all rows have a value
    op.execute("ALTER TABLE domains ALTER COLUMN community_id SET NOT NULL")

    # 5. Drop the old global unique index on slug.
    #    It was created as a unique INDEX (not a UNIQUE CONSTRAINT) by the initial
    #    migration, so DROP INDEX is correct.
    op.execute("DROP INDEX IF EXISTS ix_domains_slug")

    # 6. Add UNIQUE(community_id, slug) — slugs must be unique within a community
    op.execute("""
        ALTER TABLE domains
        ADD CONSTRAINT uq_domains_community_slug UNIQUE (community_id, slug)
    """)

    # 7. Add FK
    op.execute("""
        ALTER TABLE domains
        ADD CONSTRAINT fk_domains_community_id
        FOREIGN KEY (community_id) REFERENCES communities(id)
    """)

    # 8. Add index for community-scoped queries
    op.execute("""
        CREATE INDEX ix_domains_community_id ON domains (community_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_domains_community_id")
    op.execute("ALTER TABLE domains DROP CONSTRAINT IF EXISTS fk_domains_community_id")
    op.execute("ALTER TABLE domains DROP CONSTRAINT IF EXISTS uq_domains_community_slug")
    # Restore the old global unique index
    op.execute("CREATE UNIQUE INDEX ix_domains_slug ON domains (slug)")
    op.execute("ALTER TABLE domains DROP COLUMN IF EXISTS community_id")
    op.execute("DELETE FROM communities WHERE slug = 'test'")
