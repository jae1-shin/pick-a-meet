"""Distinguish inactive-account login attempts."""

from alembic import op


revision = "20260820_0004"
down_revision = "20260819_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_login_history_login_result", "login_history", type_="check"
    )
    op.create_check_constraint(
        "ck_login_history_login_result",
        "login_history",
        "login_result IN ('SUCCESS', 'SUCCESS_AFTER_IP_CONFIRM', 'FAILED', 'INACTIVE')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM login_history WHERE login_result = 'INACTIVE'")
    op.drop_constraint(
        "ck_login_history_login_result", "login_history", type_="check"
    )
    op.create_check_constraint(
        "ck_login_history_login_result",
        "login_history",
        "login_result IN ('SUCCESS', 'SUCCESS_AFTER_IP_CONFIRM', 'FAILED')",
    )
