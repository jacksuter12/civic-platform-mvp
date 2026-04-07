"""polymorphic signals: replace thread_id FK with target_type + target_id

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-07 00:00:00.000000

Replaces the thread_id foreign key on signals with a polymorphic
(target_type, target_id) pair so signals can be cast on threads, posts,
proposals, proposal_comments, and amendments without schema changes.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns as nullable for data migration
    op.add_column("signals", sa.Column("target_type", sa.String(length=60), nullable=True))
    op.add_column("signals", sa.Column("target_id", sa.UUID(), nullable=True))

    # 2. Migrate existing rows: all current signals were on threads
    op.execute("UPDATE signals SET target_type = 'thread', target_id = thread_id")

    # 3. Make columns NOT NULL now that data is populated
    op.alter_column("signals", "target_type", nullable=False)
    op.alter_column("signals", "target_id", nullable=False)

    # 4. Drop old unique constraint and index before dropping the column
    op.drop_constraint("uq_signal_thread_user", "signals", type_="unique")
    op.drop_index("ix_signals_thread_id", table_name="signals")

    # 5. Drop the old thread_id FK column
    op.drop_column("signals", "thread_id")

    # 6. Add new unique constraint and indexes
    op.create_unique_constraint(
        "uq_signal_user_target", "signals", ["user_id", "target_type", "target_id"]
    )
    op.create_index("ix_signals_target_type", "signals", ["target_type"])
    op.create_index("ix_signals_target_id", "signals", ["target_id"])


def downgrade() -> None:
    # Reverse: restore thread_id FK, drop polymorphic columns
    op.drop_index("ix_signals_target_id", table_name="signals")
    op.drop_index("ix_signals_target_type", table_name="signals")
    op.drop_constraint("uq_signal_user_target", "signals", type_="unique")

    op.add_column(
        "signals",
        sa.Column("thread_id", sa.UUID(), nullable=True),
    )
    # Restore from target_id where target_type was 'thread'; others become NULL
    op.execute(
        "UPDATE signals SET thread_id = target_id WHERE target_type = 'thread'"
    )
    op.alter_column("signals", "thread_id", nullable=False)
    op.create_foreign_key(
        "signals_thread_id_fkey", "signals", "threads", ["thread_id"], ["id"]
    )
    op.create_index("ix_signals_thread_id", "signals", ["thread_id"])
    op.create_unique_constraint(
        "uq_signal_thread_user", "signals", ["thread_id", "user_id"]
    )

    op.drop_column("signals", "target_id")
    op.drop_column("signals", "target_type")
