"""add proposal_comments and amendments tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-07 01:00:00.000000

Adds two new tables:
  - proposal_comments: threaded comments on proposals, PROPOSING phase only
  - amendments: proposed text changes to proposals, reviewed by proposal author

Also adds new audit_event_type values for both.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- amendment_status enum ---
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE amendment_status AS ENUM ('PENDING', 'ACCEPTED', 'REJECTED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # --- proposal_comments ---
    op.create_table(
        "proposal_comments",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_removed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("removal_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["proposal_comments.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proposal_comments_proposal_id", "proposal_comments", ["proposal_id"])
    op.create_index("ix_proposal_comments_author_id", "proposal_comments", ["author_id"])

    # --- amendments ---
    op.create_table(
        "amendments",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("proposed_text", sa.Text(), nullable=False),
        sa.Column("rationale", sa.String(length=1000), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACCEPTED", "REJECTED", name="amendment_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_amendments_proposal_id", "amendments", ["proposal_id"])
    op.create_index("ix_amendments_status", "amendments", ["status"])

    # --- new audit event types (name-based, uppercase) ---
    for event in (
        "PROPOSAL_COMMENT_CREATED",
        "PROPOSAL_COMMENT_REMOVED",
        "AMENDMENT_SUBMITTED",
        "AMENDMENT_ACCEPTED",
        "AMENDMENT_REJECTED",
    ):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{event}'")


def downgrade() -> None:
    op.drop_index("ix_amendments_status", table_name="amendments")
    op.drop_index("ix_amendments_proposal_id", table_name="amendments")
    op.drop_table("amendments")

    op.drop_index("ix_proposal_comments_author_id", table_name="proposal_comments")
    op.drop_index("ix_proposal_comments_proposal_id", table_name="proposal_comments")
    op.drop_table("proposal_comments")

    op.execute("DROP TYPE IF EXISTS amendment_status")
    # PostgreSQL does not support removing enum values; audit_event_type entries remain.
