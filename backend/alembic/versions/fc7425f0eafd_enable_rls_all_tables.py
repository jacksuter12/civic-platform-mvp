"""enable_rls_all_tables

Revision ID: fc7425f0eafd
Revises: i3c4d5e6f7g8
Create Date: 2026-05-14 16:58:16.664775

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc7425f0eafd'
down_revision: Union[str, None] = 'i3c4d5e6f7g8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = [
    "alembic_version",
    "allocation_decisions",
    "amendments",
    "annotation_reactions",
    "annotations",
    "annotator_requests",
    "audit_logs",
    "communities",
    "community_memberships",
    "domains",
    "facilitator_requests",
    "funding_pools",
    "posts",
    "proposal_comments",
    "proposal_versions",
    "proposals",
    "signals",
    "threads",
    "users",
    "votes",
]


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
