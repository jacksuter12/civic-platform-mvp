"""add community_id to audit_logs

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-12 00:05:00.000000

Adds a nullable community_id FK to audit_logs.
Platform-level events (user registration, annotator grants, etc.) leave it NULL.
Community-scoped events (thread created, vote cast, etc.) will carry the
community UUID once Session 3 route updates land.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stays nullable — platform-level events have no community
    op.execute("ALTER TABLE audit_logs ADD COLUMN community_id UUID NULL")
    op.execute("""
        ALTER TABLE audit_logs
        ADD CONSTRAINT fk_audit_logs_community_id
        FOREIGN KEY (community_id) REFERENCES communities(id)
    """)
    op.execute("CREATE INDEX ix_audit_logs_community_id ON audit_logs (community_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_community_id")
    op.execute(
        "ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS fk_audit_logs_community_id"
    )
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS community_id")
