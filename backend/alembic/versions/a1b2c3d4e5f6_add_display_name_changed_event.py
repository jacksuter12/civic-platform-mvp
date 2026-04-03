"""add display_name_changed audit event

Revision ID: a1b2c3d4e5f6
Revises: 0b94242b3368
Create Date: 2026-04-02 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0b94242b3368'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL native enum uses the member NAME (uppercase), not the Python str value.
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'DISPLAY_NAME_CHANGED'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op.
    pass
