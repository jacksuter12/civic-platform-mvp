"""add proposal versioning

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-07 02:00:00.000000

Adds:
  - proposals.current_version_number (integer, default 1)
  - proposal_versions table (immutable snapshots of proposal content before edits)
  - PROPOSAL_EDITED audit event type
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add current_version_number to existing proposals (backfill with 1)
    op.add_column(
        "proposals",
        sa.Column(
            "current_version_number",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    # 2. Create proposal_versions table
    op.create_table(
        "proposal_versions",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("edit_summary", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", "version_number", name="uq_proposal_version"),
    )
    op.create_index("ix_proposal_versions_proposal_id", "proposal_versions", ["proposal_id"])

    # 3. New audit event type
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'PROPOSAL_EDITED'")


def downgrade() -> None:
    op.drop_index("ix_proposal_versions_proposal_id", table_name="proposal_versions")
    op.drop_table("proposal_versions")
    op.drop_column("proposals", "current_version_number")
    # PostgreSQL does not support removing enum values; PROPOSAL_EDITED entry remains.
