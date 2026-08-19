"""Add the public Host information visibility setting."""

from alembic import op
import sqlalchemy as sa


revision = "20260820_0007"
down_revision = "20260820_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registration_schedule",
        sa.Column(
            "show_host_information",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("registration_schedule", "show_host_information")
