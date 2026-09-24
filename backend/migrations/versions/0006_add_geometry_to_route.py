"""Add geometry_field to plan.

Revision ID: 0006_add_geometry_to_route
Revises: 0005_stop_request_cascade
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_add_geometry_to_route"
down_revision = "0005_stop_request_cascade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("route", sa.Column("geometry", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("route", "geometry")
