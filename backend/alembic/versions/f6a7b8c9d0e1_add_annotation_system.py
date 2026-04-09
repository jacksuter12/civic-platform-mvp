"""add annotation system

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-09 00:00:00.000000

Adds:
  - annotations table (target-agnostic; v1 target_type is 'wiki')
  - annotation_reactions table (endorse / needs_work; one per user per annotation)
  - users.is_annotator boolean column (orthogonal capability flag)
  - reaction_type DB enum
  - seven new audit_event_type values for annotation actions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_reaction_type = pg.ENUM("ENDORSE", "NEEDS_WORK", name="reaction_type")


def upgrade() -> None:
    # 1. Create reaction_type enum
    _reaction_type.create(op.get_bind(), checkfirst=True)

    # 2. Create annotations table
    op.create_table(
        "annotations",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # target_type is a plain string (not a DB enum) so adding new target types
        # never requires ALTER TYPE. Current allowed values: wiki, post, proposal, document.
        sa.Column("target_type", sa.String(length=60), nullable=False),
        # target_id is a string to support wiki slugs and future UUID targets uniformly.
        sa.Column("target_id", sa.String(length=255), nullable=False),
        # Opaque Hypothesis anchor selectors. Backend stores and returns verbatim.
        sa.Column("anchor_data", pg.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        # Nullable: top-level annotations have no parent.
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        # updated_at: null means never edited; set by API layer on edit.
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # deleted_at: soft delete; API layer tombstones the body when set.
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["annotations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Primary query: all annotations on a given target.
    op.create_index(
        "ix_annotations_target_type_id", "annotations", ["target_type", "target_id"]
    )
    op.create_index("ix_annotations_author_id", "annotations", ["author_id"])
    op.create_index("ix_annotations_parent_id", "annotations", ["parent_id"])

    # 3. Create annotation_reactions table
    op.create_table(
        "annotation_reactions",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("annotation_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "reaction",
            pg.ENUM("ENDORSE", "NEEDS_WORK", name="reaction_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # CASCADE: reactions are removed if the annotation is hard-deleted
        # (application layer always soft-deletes; this covers DB-level cleanup only).
        sa.ForeignKeyConstraint(
            ["annotation_id"], ["annotations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "annotation_id", "user_id", name="uq_annotation_reaction_user"
        ),
    )
    op.create_index(
        "ix_annotation_reactions_annotation_id",
        "annotation_reactions",
        ["annotation_id"],
    )
    op.create_index(
        "ix_annotation_reactions_user_id", "annotation_reactions", ["user_id"]
    )

    # 4. Add is_annotator to users (default false; all existing users get false)
    op.add_column(
        "users",
        sa.Column(
            "is_annotator",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # 5. Register new audit event types
    for event in (
        "ANNOTATION_CREATED",
        "ANNOTATION_UPDATED",
        "ANNOTATION_DELETED",
        "ANNOTATION_REACTION_ADDED",
        "ANNOTATION_REACTION_REMOVED",
        "USER_ANNOTATOR_GRANTED",
        "USER_ANNOTATOR_REVOKED",
    ):
        op.execute(f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{event}'")


def downgrade() -> None:
    # Reverse in opposite order.

    # Note: PostgreSQL does not support removing values from an enum type,
    # so audit_event_type additions from step 5 are left in place on downgrade.
    # This matches the convention in all previous migrations in this project.

    # 4. Remove is_annotator column
    op.drop_column("users", "is_annotator")

    # 3. Drop annotation_reactions
    op.drop_index("ix_annotation_reactions_user_id", table_name="annotation_reactions")
    op.drop_index(
        "ix_annotation_reactions_annotation_id", table_name="annotation_reactions"
    )
    op.drop_table("annotation_reactions")

    # 2. Drop annotations
    op.drop_index("ix_annotations_parent_id", table_name="annotations")
    op.drop_index("ix_annotations_author_id", table_name="annotations")
    op.drop_index("ix_annotations_target_type_id", table_name="annotations")
    op.drop_table("annotations")

    # 1. Drop reaction_type enum
    op.execute("DROP TYPE IF EXISTS reaction_type")
