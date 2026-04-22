"""add community_id to threads

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-04-12 00:03:00.000000

Derives community_id from the thread's domain (thread → domain → community).
All existing threads end up in the test/legacy community.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add column (nullable for backfill)
    op.execute("ALTER TABLE threads ADD COLUMN community_id UUID NULL")

    # 2. Derive community from the thread's domain
    op.execute("""
        UPDATE threads
        SET community_id = (
            SELECT community_id FROM domains WHERE domains.id = threads.domain_id
        )
    """)

    # 3. Enforce NOT NULL
    op.execute("ALTER TABLE threads ALTER COLUMN community_id SET NOT NULL")

    # 4. Add FK
    op.execute("""
        ALTER TABLE threads
        ADD CONSTRAINT fk_threads_community_id
        FOREIGN KEY (community_id) REFERENCES communities(id)
    """)

    # 5. Add index
    op.execute("CREATE INDEX ix_threads_community_id ON threads (community_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_threads_community_id")
    op.execute("ALTER TABLE threads DROP CONSTRAINT IF EXISTS fk_threads_community_id")
    op.execute("ALTER TABLE threads DROP COLUMN IF EXISTS community_id")
