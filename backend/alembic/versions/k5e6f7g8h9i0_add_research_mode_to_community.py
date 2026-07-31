"""add research_mode to communities

Hand-authored — do NOT regenerate with --autogenerate. app/models/__init__.py
does not import notification.py, so autogenerate would emit a spurious
DROP TABLE notifications.

No RLS statement here: CLAUDE.md constraint #11 covers new tables in `public`,
not new columns on existing ones. `communities` already has RLS enabled.

Revision ID: k5e6f7g8h9i0
Revises: b0d77cb5b780
Create Date: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k5e6f7g8h9i0"
down_revision: Union[str, None] = "b0d77cb5b780"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "communities",
        sa.Column(
            "research_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("communities", "research_mode")
