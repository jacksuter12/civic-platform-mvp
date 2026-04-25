"""proposal_version track changes schema

Revision ID: a0b1c2d3e4f5
Revises: 44bcb3054b32
Create Date: 2026-04-25 10:00:00.000000

Adds forward-compatible columns to proposal_versions for the future
Track Changes feature (PR-style suggested revisions). No behavior change —
existing rows are backfilled with safe defaults. Track Changes business
logic is Chunk B.

Columns added:
  status          — 'accepted' for all existing rows
  authored_by_id  — copied from proposal_versions.author_id
  parent_version_id — NULL (no suggestion history yet)
  decided_at      — copied from proposal_versions.created_at
  decided_by_id   — copied from proposals.created_by_id
  decision_reason — NULL
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from alembic import op

revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "44bcb3054b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the PostgreSQL enum type
    op.execute(
        "CREATE TYPE proposal_version_status AS ENUM "
        "('accepted', 'suggested', 'rejected', 'withdrawn')"
    )

    # 2. Add status column (NOT NULL with default 'accepted')
    op.add_column(
        "proposal_versions",
        sa.Column(
            "status",
            sa.Enum(
                "accepted", "suggested", "rejected", "withdrawn",
                name="proposal_version_status",
                create_type=False,
            ),
            nullable=False,
            server_default="accepted",
        ),
    )

    # 3. authored_by_id
    op.add_column(
        "proposal_versions",
        sa.Column("authored_by_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_proposal_versions_authored_by_id_users",
        "proposal_versions",
        "users",
        ["authored_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4. parent_version_id (self-referential)
    op.add_column(
        "proposal_versions",
        sa.Column("parent_version_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_proposal_versions_parent_version_id",
        "proposal_versions",
        "proposal_versions",
        ["parent_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 5. decided_at
    op.add_column(
        "proposal_versions",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 6. decided_by_id
    op.add_column(
        "proposal_versions",
        sa.Column("decided_by_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_proposal_versions_decided_by_id_users",
        "proposal_versions",
        "users",
        ["decided_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 7. decision_reason
    op.add_column(
        "proposal_versions",
        sa.Column("decision_reason", sa.Text(), nullable=True),
    )

    # 8. Backfill existing rows:
    #   authored_by_id  = proposal_versions.author_id (who made the edit)
    #   decided_by_id   = proposals.created_by_id (proposal owner who accepted)
    #   decided_at      = proposal_versions.created_at (decided at moment of creation)
    op.execute("""
        UPDATE proposal_versions pv
        SET authored_by_id = pv.author_id,
            decided_by_id  = p.created_by_id,
            decided_at     = pv.created_at
        FROM proposals p
        WHERE pv.proposal_id = p.id
    """)


def downgrade() -> None:
    op.drop_constraint(
        "fk_proposal_versions_decided_by_id_users",
        "proposal_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_proposal_versions_parent_version_id",
        "proposal_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_proposal_versions_authored_by_id_users",
        "proposal_versions",
        type_="foreignkey",
    )
    op.drop_column("proposal_versions", "decision_reason")
    op.drop_column("proposal_versions", "decided_by_id")
    op.drop_column("proposal_versions", "decided_at")
    op.drop_column("proposal_versions", "parent_version_id")
    op.drop_column("proposal_versions", "authored_by_id")
    op.drop_column("proposal_versions", "status")

    op.execute("DROP TYPE IF EXISTS proposal_version_status")
