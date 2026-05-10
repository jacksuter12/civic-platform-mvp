"""fix enum casing for membership_request_status and audit_event_type

Revision ID: i3c4d5e6f7g8
Revises: h2b3c4d5e6f7
Create Date: 2026-05-10 00:00:00.000000

Root cause:
  SQLAlchemy's SAEnum serialises Python enum *names* (PENDING, APPROVED …)
  to the database, not the string *values* (pending, approved …).
  The initial audit_event_type enum was correctly created with uppercase
  names (USER_REGISTERED, etc.), but h2b3c4d5e6f7 created the new
  membership_request_status type with lowercase values AND added the four
  new audit_event_type values in lowercase — both mismatching what
  SQLAlchemy sends at query time.

Fixes:
  1. Recreate membership_request_status with uppercase values
     (PENDING / APPROVED / DENIED).  The table has no rows yet so we can
     drop and recreate the column type safely.
  2. Add the four new audit_event_type values in uppercase, matching the
     naming convention set by the original migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg


revision: str = "i3c4d5e6f7g8"
down_revision: Union[str, None] = "h2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Fix membership_request_status: recreate with uppercase values
    # -------------------------------------------------------------------------
    # Alter the column to TEXT first so we can drop the old enum type
    op.execute(
        "ALTER TABLE membership_requests "
        "ALTER COLUMN status TYPE TEXT USING status::TEXT"
    )
    op.execute("DROP TYPE IF EXISTS membership_request_status")
    op.execute(
        "CREATE TYPE membership_request_status AS ENUM ('PENDING', 'APPROVED', 'DENIED')"
    )
    op.execute(
        "ALTER TABLE membership_requests "
        "ALTER COLUMN status TYPE membership_request_status "
        "USING status::membership_request_status"
    )

    # -------------------------------------------------------------------------
    # 2. Fix audit_event_type: add the four new values in uppercase
    # -------------------------------------------------------------------------
    # IF NOT EXISTS is safe: if a previous migration added the lowercase version
    # it won't interfere (we're adding the correctly-cased uppercase version).
    for value in (
        "COMMUNITY_SETTINGS_UPDATED",
        "MEMBERSHIP_REQUEST_SUBMITTED",
        "MEMBERSHIP_REQUEST_APPROVED",
        "MEMBERSHIP_REQUEST_DENIED",
    ):
        op.execute(
            f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    # Revert membership_request_status back to lowercase values.
    # audit_event_type values cannot be removed; leave them in place.
    op.execute(
        "ALTER TABLE membership_requests "
        "ALTER COLUMN status TYPE TEXT USING status::TEXT"
    )
    op.execute("DROP TYPE IF EXISTS membership_request_status")
    op.execute(
        "CREATE TYPE membership_request_status AS ENUM ('pending', 'approved', 'denied')"
    )
    op.execute(
        "ALTER TABLE membership_requests "
        "ALTER COLUMN status TYPE membership_request_status "
        "USING status::membership_request_status"
    )
