"""add is_synthetic to users

Marks an account as operated by software rather than a person, so a human can
always tell who they are reading. Set by a platform admin, never self-asserted
at registration.

Hand-authored — do NOT regenerate with --autogenerate. app/models/__init__.py
does not import notification.py, so autogenerate would emit a spurious
DROP TABLE notifications.

The two new audit_event_type values are added in UPPERCASE. SQLAlchemy's
SAEnum serialises Python enum *names*, not values — see migration
i3c4d5e6f7g8, which exists because that was got wrong once already.

No RLS statement: CLAUDE.md constraint #11 covers new tables, not new columns.

Revision ID: m6f7g8h9i0j1
Revises: k5e6f7g8h9i0
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "m6f7g8h9i0j1"
down_revision: Union[str, None] = "k5e6f7g8h9i0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_synthetic",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'USER_MARKED_SYNTHETIC'"
    )
    op.execute(
        "ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'USER_UNMARKED_SYNTHETIC'"
    )


def downgrade() -> None:
    op.drop_column("users", "is_synthetic")
    # PostgreSQL cannot remove values from an enum type, so the two
    # audit_event_type values stay. They are inert without the column.
