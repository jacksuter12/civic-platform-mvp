"""add annotation resolve and proposal body html

Revision ID: 44bcb3054b32
Revises: d6e7f8a9b0c1
Create Date: 2026-04-24 14:26:53.506545

Adds resolve/unresolve support to annotations and server-rendered HTML to proposals.

Changes:
  annotations: resolved_at (timestamp), resolved_by_id (FK to users)
  proposals: body_html (TEXT, server-rendered markdown)
  proposal_versions: body_html (TEXT, server-rendered markdown)
  audit_event_type enum: ANNOTATION_RESOLVED, ANNOTATION_UNRESOLVED

Note: PostgreSQL does not support removing enum values, so downgrade cannot
reverse the audit_event_type additions. This matches convention in all prior migrations.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from alembic import op

from app.core.markdown import render_markdown

# revision identifiers, used by Alembic.
revision: str = "44bcb3054b32"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend audit_event_type enum
    for value in ("annotation_resolved", "annotation_unresolved"):
        op.execute(
            f"ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS '{value}'"
        )

    # 2. annotations: resolve tracking columns
    op.add_column(
        "annotations",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "annotations",
        sa.Column(
            "resolved_by_id",
            PG_UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_annotations_resolved_by_id_users",
        "annotations",
        "users",
        ["resolved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. proposals: rendered HTML column
    op.add_column(
        "proposals",
        sa.Column("body_html", sa.Text(), server_default="", nullable=False),
    )

    # 4. proposal_versions: rendered HTML column
    op.add_column(
        "proposal_versions",
        sa.Column("body_html", sa.Text(), server_default="", nullable=False),
    )

    # 5. Backfill body_html from description for existing rows
    bind = op.get_bind()

    proposals = bind.execute(sa.text("SELECT id, description FROM proposals")).fetchall()
    for row in proposals:
        rendered = render_markdown(row[1] or "")
        bind.execute(
            sa.text("UPDATE proposals SET body_html = :html WHERE id = :id"),
            {"html": rendered, "id": row[0]},
        )

    versions = bind.execute(
        sa.text("SELECT id, description FROM proposal_versions")
    ).fetchall()
    for row in versions:
        rendered = render_markdown(row[1] or "")
        bind.execute(
            sa.text("UPDATE proposal_versions SET body_html = :html WHERE id = :id"),
            {"html": rendered, "id": row[0]},
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_annotations_resolved_by_id_users", "annotations", type_="foreignkey"
    )
    op.drop_column("annotations", "resolved_by_id")
    op.drop_column("annotations", "resolved_at")
    op.drop_column("proposal_versions", "body_html")
    op.drop_column("proposals", "body_html")
    # PostgreSQL does not support removing enum values; annotation_resolved and
    # annotation_unresolved remain in audit_event_type after downgrade.
