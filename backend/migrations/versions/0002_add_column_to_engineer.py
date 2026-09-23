import sqlalchemy as sa
from alembic import op

revision = "0002_add_column_to_engineer"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("engineer", sa.Column("start_lat", sa.Double(), nullable=True))
    op.add_column("engineer", sa.Column("start_lon", sa.Double(), nullable=True))


def downgrade() -> None:
    op.drop_column("engineer", "start_lon")
    op.drop_column("engineer", "start_lat")
