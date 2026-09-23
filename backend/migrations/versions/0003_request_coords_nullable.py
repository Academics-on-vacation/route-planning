"""Make request.lat/lon nullable.

Revision ID: 0003_request_coords_nullable
Revises: 0002_add_column_to_engineer
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_request_coords_nullable"
down_revision = "0002_add_column_to_engineer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("request", "lat", existing_type=sa.Double(), nullable=True)
    op.alter_column("request", "lon", existing_type=sa.Double(), nullable=True)


def downgrade() -> None:
    op.alter_column("request", "lat", existing_type=sa.Double(), nullable=False)
    op.alter_column("request", "lon", existing_type=sa.Double(), nullable=False)
