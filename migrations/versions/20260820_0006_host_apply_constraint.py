"""Require Host users to have application permission disabled."""

from alembic import op


revision = "20260820_0006"
down_revision = "20260820_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE member SET apply_enabled = false WHERE host_enabled = true")
    op.create_check_constraint(
        "ck_member_host_without_apply",
        "member",
        "NOT (host_enabled AND apply_enabled)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_member_host_without_apply", "member", type_="check"
    )
