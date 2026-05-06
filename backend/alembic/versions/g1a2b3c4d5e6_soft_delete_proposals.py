"""soft delete proposals

Revision ID: g1a2b3c4d5e6
Revises: f0a1b2c3d4e5
Create Date: 2026-05-06 00:00:00.000000

Adds soft-delete columns to proposals table:
  - deleted_at: nullable timestamptz
  - deleted_by_id: nullable FK to users.id (SET NULL on delete)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column(
            "deleted_by_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("proposals", "deleted_by_id")
    op.drop_column("proposals", "deleted_at")
