"""fix audit_event_type enum case mismatch

Revision ID: f0a1b2c3d4e5
Revises: e8f9a0b1c2d3
Create Date: 2026-05-04 00:00:00.000000

Background
----------
SQLAlchemy serializes Python enum members by their `.name` attribute (uppercase)
when writing to a native PostgreSQL enum column.  The initial annotation migration
(f6a7b8c9d0e1) correctly added UPPERCASE values.  Several later migrations
accidentally used lowercase strings, creating a mismatch:

  DB has lowercase      SQLAlchemy sends uppercase  → PostgreSQL raises ERROR
  ──────────────────────────────────────────────────────────────────────────────
  annotation_resolved        ANNOTATION_RESOLVED
  annotation_unresolved      ANNOTATION_UNRESOLVED
  community_updated          COMMUNITY_UPDATED
  annotator_request_*        ANNOTATOR_REQUEST_*

Additionally, four annotation action types were added to the Python enum but
never added to the PostgreSQL enum at all:
  ANNOTATION_FEATURED / ANNOTATION_UNFEATURED / ANNOTATION_ORPHANED / ANNOTATION_MODERATED

This migration adds all missing UPPERCASE values using IF NOT EXISTS so it is
safe to run repeatedly and does not conflict with the lowercase values already
present (PostgreSQL enums are case-sensitive; both variants coexist).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# All uppercase values that must exist in the audit_event_type PostgreSQL enum.
# IF NOT EXISTS means re-running is safe and won't duplicate existing values.
_MISSING_UPPERCASE = [
    # From d6e7f8a9b0c1 (added lowercase by mistake)
    "COMMUNITY_UPDATED",
    # From 44bcb3054b32 (added lowercase by mistake)
    "ANNOTATION_RESOLVED",
    "ANNOTATION_UNRESOLVED",
    # From e8f9a0b1c2d3 (added lowercase by mistake)
    "ANNOTATOR_REQUEST_SUBMITTED",
    "ANNOTATOR_REQUEST_APPROVED",
    "ANNOTATOR_REQUEST_DENIED",
    # Never added to the DB at all (Python enum only)
    "ANNOTATION_FEATURED",
    "ANNOTATION_UNFEATURED",
    "ANNOTATION_ORPHANED",
    "ANNOTATION_MODERATED",
]


def upgrade() -> None:
    for value in _MISSING_UPPERCASE:
        op.execute(
            f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; leave them in place.
    pass
