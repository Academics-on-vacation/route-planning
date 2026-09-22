"""Create regions, engineers, requests and route cache.

Revision ID: 0001_initial_schema
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "region",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("office_address", sa.String(), nullable=False),
        sa.Column("office_lat", sa.Double(), nullable=False),
        sa.Column("office_lon", sa.Double(), nullable=False),
        sa.UniqueConstraint("title"),
    )
    op.create_table(
        "engineer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("transport", sa.String(16), server_default="transit", nullable=False),
        sa.Column(
            "skills", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("shift_start", sa.Time(), server_default=sa.text("'09:00'"), nullable=False),
        sa.Column("shift_end", sa.Time(), server_default=sa.text("'22:00'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("start_lat", sa.Double(), nullable=True),
        sa.Column("start_lon", sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("region_id", "name"),
        sa.CheckConstraint("shift_end > shift_start", name="ck_engineer_shift"),
    )
    op.create_index("ix_engineer_region", "engineer", ["region_id"])
    op.create_table(
        "request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(32), nullable=False),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("district", sa.String(128), nullable=True),
        sa.Column("lat", sa.Double(), nullable=False),
        sa.Column("lon", sa.Double(), nullable=False),
        sa.Column("work_type", sa.String(48), nullable=False),
        sa.Column("hd_type", sa.String(128), nullable=True),
        sa.Column("skill", sa.String(16), nullable=False),
        sa.Column("duration_min", sa.SmallInteger(), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default=sa.text("100"), nullable=False),
        sa.Column("required_transport", sa.String(16), nullable=True),
        sa.Column(
            "equipment", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("fact_engineer_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fact_engineer_id"], ["engineer.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("region_id", "external_id", "window_start"),
        sa.CheckConstraint("duration_min > 0", name="ck_request_duration"),
        sa.CheckConstraint("window_end > window_start", name="ck_request_window"),
    )
    op.create_index("ix_request_planning", "request", ["region_id", "window_start"])
    op.create_index("ix_request_skill", "request", ["skill"])
    op.create_index("ix_request_fact", "request", ["fact_engineer_id"])
    op.create_table(
        "route_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("from_lat", sa.Double(), nullable=False),
        sa.Column("from_lon", sa.Double(), nullable=False),
        sa.Column("to_lat", sa.Double(), nullable=False),
        sa.Column("to_lon", sa.Double(), nullable=False),
        sa.Column("departure_at", sa.DateTime(), nullable=False),
        sa.Column("minutes", sa.SmallInteger(), nullable=False),
        sa.Column("km", sa.Double(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "transport",
            "from_lat",
            "from_lon",
            "to_lat",
            "to_lon",
            "departure_at",
            name="uq_route_cache_leg",
        ),
    )
    op.create_index("ix_route_cache_departure", "route_cache", ["departure_at"])


def downgrade() -> None:
    op.drop_table("route_cache")
    op.drop_table("request")
    op.drop_table("engineer")
    op.drop_table("region")
