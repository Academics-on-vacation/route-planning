"""Create plan, route and stop tables for saved/replayable plans.

Revision ID: 0004_plan_route_stop
Revises: 0003_request_coords_nullable
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_plan_route_stop"
down_revision = "0003_request_coords_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("solver", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column(
            "metrics", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["region_id"], ["region.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "uq_plan_active_per_day",
        "plan",
        ["region_id", "work_date"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "route",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("engineer_id", sa.Integer(), nullable=False),
        sa.Column("distance_km", sa.Double(), server_default=sa.text("0"), nullable=False),
        sa.Column("travel_min", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("service_min", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("wait_min", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plan.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["engineer_id"], ["engineer.id"]),
    )

    op.create_table(
        "stop",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("depart_at", sa.DateTime(), nullable=False),
        sa.Column("arrive_at", sa.DateTime(), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("travel_min", sa.SmallInteger(), nullable=False),
        sa.Column("travel_km", sa.Double(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["route.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["request.id"]),
    )
    op.create_index("ix_stop_route", "stop", ["route_id"])


def downgrade() -> None:
    op.drop_table("stop")
    op.drop_table("route")
    op.drop_index("uq_plan_active_per_day", table_name="plan")
    op.drop_table("plan")
