"""add communities table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-12 00:00:00.000000

Adds:
  - community_type ENUM: GEOGRAPHIC, ORGANIZATIONAL, INSTITUTIONAL, TOPICAL, TECHNICAL
  - communities table (slug globally unique; created_by_id nullable for seed data)
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create community_type enum (idempotent)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE community_type AS ENUM (
                'GEOGRAPHIC', 'ORGANIZATIONAL', 'INSTITUTIONAL', 'TOPICAL', 'TECHNICAL'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # 2. Create communities table
    op.execute("""
        CREATE TABLE IF NOT EXISTS communities (
            id                      UUID        NOT NULL DEFAULT gen_random_uuid(),
            slug                    TEXT        NOT NULL,
            name                    TEXT        NOT NULL,
            description             TEXT        NOT NULL,
            community_type          community_type NOT NULL,
            boundary_desc           TEXT        NOT NULL,
            verification_method     TEXT        NOT NULL,
            is_public               BOOLEAN     NOT NULL DEFAULT TRUE,
            is_invite_only          BOOLEAN     NOT NULL DEFAULT FALSE,
            default_phase_durations JSONB       NULL,
            is_active               BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by_id           UUID        REFERENCES users(id),
            PRIMARY KEY (id),
            CONSTRAINT uq_communities_slug UNIQUE (slug)
        )
    """)

    # 3. Index on slug (the UNIQUE constraint also creates one, but we add an
    #    explicit named index for consistent Alembic tracking)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_communities_slug ON communities (slug)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_communities_slug")
    op.execute("DROP TABLE IF EXISTS communities")
    op.execute("DROP TYPE IF EXISTS community_type")
