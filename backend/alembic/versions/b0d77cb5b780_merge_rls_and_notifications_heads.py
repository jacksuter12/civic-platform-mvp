"""merge rls and notifications heads

Revision ID: b0d77cb5b780
Revises: fc7425f0eafd, j4d5e6f7g8h9
Create Date: 2026-05-14 19:07:32.566258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0d77cb5b780'
down_revision: Union[str, None] = ('fc7425f0eafd', 'j4d5e6f7g8h9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
