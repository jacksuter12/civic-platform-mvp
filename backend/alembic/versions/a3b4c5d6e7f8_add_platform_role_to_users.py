"""add platform_role to users

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-04-12 00:06:00.000000

Adds a platform_role ENUM column to users (USER / PLATFORM_ADMIN).
Existing admin-tier users are promoted to PLATFORM_ADMIN.
The global 'admin' tier continues to exist; platform_role is an orthogonal
flag that governs platform-level capabilities (community creation, annotator
management) independently of the tier hierarchy.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create platform_role enum (idempotent)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE platform_role AS ENUM ('USER', 'PLATFORM_ADMIN');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # 2. Add column with default 'USER'
    op.execute("""
        ALTER TABLE users
        ADD COLUMN platform_role platform_role NOT NULL DEFAULT 'USER'
    """)

    # 3. Promote existing admin-tier users to PLATFORM_ADMIN
    op.execute("""
        UPDATE users SET platform_role = 'PLATFORM_ADMIN' WHERE tier = 'ADMIN'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS platform_role")
    op.execute("DROP TYPE IF EXISTS platform_role")
