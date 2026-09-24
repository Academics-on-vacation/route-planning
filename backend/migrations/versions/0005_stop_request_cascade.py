"""Cascade-delete stop rows when their request is deleted.

Revision ID: 0005_stop_request_cascade
Revises: 0004_plan_route_stop
"""

from alembic import op

revision = "0005_stop_request_cascade"
down_revision = "0004_plan_route_stop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("stop_request_id_fkey", "stop", type_="foreignkey")
    op.create_foreign_key(
        "stop_request_id_fkey",
        "stop",
        "request",
        ["request_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("stop_request_id_fkey", "stop", type_="foreignkey")
    op.create_foreign_key(
        "stop_request_id_fkey",
        "stop",
        "request",
        ["request_id"],
        ["id"],
    )
