"""add facilitator requests

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum type — idempotent via exception handler (handles partial previous runs)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE facilitator_request_status AS ENUM ('PENDING', 'APPROVED', 'DENIED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Create table via raw SQL to avoid SQLAlchemy re-emitting CREATE TYPE
    op.execute("""
        CREATE TABLE IF NOT EXISTS facilitator_requests (
            id          UUID        NOT NULL DEFAULT gen_random_uuid(),
            user_id     UUID        NOT NULL REFERENCES users(id),
            reason      TEXT        NOT NULL,
            status      facilitator_request_status NOT NULL DEFAULT 'PENDING',
            reviewed_by_id UUID     REFERENCES users(id),
            reviewed_at TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_facilitator_requests_user_id
        ON facilitator_requests (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_facilitator_requests_status
        ON facilitator_requests (status)
    """)

    # New audit event types
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'FACILITATOR_REQUEST_SUBMITTED'"
    )
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'FACILITATOR_REQUEST_APPROVED'"
    )
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'FACILITATOR_REQUEST_DENIED'"
    )


def downgrade() -> None:
    op.drop_index('ix_facilitator_requests_status', 'facilitator_requests')
    op.drop_index('ix_facilitator_requests_user_id', 'facilitator_requests')
    op.drop_table('facilitator_requests')
    op.execute('DROP TYPE facilitator_request_status')
    # PostgreSQL does not support removing enum values; audit_event_type entries remain.
