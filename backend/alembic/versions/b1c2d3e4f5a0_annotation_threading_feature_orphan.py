"""annotation threading feature orphan

Revision ID: b1c2d3e4f5a0
Revises: a0b1c2d3e4f5
Create Date: 2026-04-25 10:05:00.000000

Adds columns to annotations for the proposal annotation system:
  featured_at     — when a facilitator pinned this annotation
  featured_by_id  — who featured it
  orphaned_at     — when the client reported the anchor no longer resolves

Also adds a (target_type, target_id, created_at) index for efficient
list + sort queries on proposal annotations.

Note: parent_id already exists from the initial schema migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from alembic import op

revision: str = "b1c2d3e4f5a0"
down_revision: Union[str, None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # featured_at
    op.add_column(
        "annotations",
        sa.Column("featured_at", sa.DateTime(timezone=True), nullable=True),
    )

    # featured_by_id
    op.add_column(
        "annotations",
        sa.Column("featured_by_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_annotations_featured_by_id_users",
        "annotations",
        "users",
        ["featured_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # orphaned_at
    op.add_column(
        "annotations",
        sa.Column("orphaned_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Composite index for efficient list+sort queries
    op.create_index(
        "ix_annotations_target_type_id_created",
        "annotations",
        ["target_type", "target_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_annotations_target_type_id_created",
        table_name="annotations",
        if_exists=True,
    )
    op.drop_column("annotations", "orphaned_at")
    op.drop_constraint(
        "fk_annotations_featured_by_id_users",
        "annotations",
        type_="foreignkey",
    )
    op.drop_column("annotations", "featured_by_id")
    op.drop_column("annotations", "featured_at")
