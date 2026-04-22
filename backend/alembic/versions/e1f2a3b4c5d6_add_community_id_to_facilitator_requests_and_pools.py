"""add community_id to facilitator_requests and funding_pools

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-04-12 00:04:00.000000

facilitator_requests: all legacy requests assigned to the test community.
funding_pools: community derived from pool's domain (pool → domain → community).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- facilitator_requests ---
    op.execute("ALTER TABLE facilitator_requests ADD COLUMN community_id UUID NULL")
    op.execute("""
        UPDATE facilitator_requests
        SET community_id = (SELECT id FROM communities WHERE slug = 'test')
    """)
    op.execute(
        "ALTER TABLE facilitator_requests ALTER COLUMN community_id SET NOT NULL"
    )
    op.execute("""
        ALTER TABLE facilitator_requests
        ADD CONSTRAINT fk_facilitator_requests_community_id
        FOREIGN KEY (community_id) REFERENCES communities(id)
    """)
    op.execute("""
        CREATE INDEX ix_facilitator_requests_community_id
        ON facilitator_requests (community_id)
    """)

    # --- funding_pools ---
    op.execute("ALTER TABLE funding_pools ADD COLUMN community_id UUID NULL")
    op.execute("""
        UPDATE funding_pools fp
        SET community_id = d.community_id
        FROM domains d
        WHERE d.id = fp.domain_id
    """)
    op.execute("ALTER TABLE funding_pools ALTER COLUMN community_id SET NOT NULL")
    op.execute("""
        ALTER TABLE funding_pools
        ADD CONSTRAINT fk_funding_pools_community_id
        FOREIGN KEY (community_id) REFERENCES communities(id)
    """)
    op.execute("""
        CREATE INDEX ix_funding_pools_community_id ON funding_pools (community_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_funding_pools_community_id")
    op.execute(
        "ALTER TABLE funding_pools DROP CONSTRAINT IF EXISTS fk_funding_pools_community_id"
    )
    op.execute("ALTER TABLE funding_pools DROP COLUMN IF EXISTS community_id")

    op.execute("DROP INDEX IF EXISTS ix_facilitator_requests_community_id")
    op.execute(
        "ALTER TABLE facilitator_requests "
        "DROP CONSTRAINT IF EXISTS fk_facilitator_requests_community_id"
    )
    op.execute("ALTER TABLE facilitator_requests DROP COLUMN IF EXISTS community_id")
