"""Add the global registration opening schedule."""

from alembic import op
import sqlalchemy as sa


revision = "20260820_0005"
down_revision = "20260820_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registration_schedule",
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("schedule_id = 1", name="ck_registration_schedule_singleton"),
        sa.PrimaryKeyConstraint("schedule_id", name="pk_registration_schedule"),
    )
    op.execute(
        "INSERT INTO registration_schedule (schedule_id, opens_at) VALUES (1, NULL)"
    )


def downgrade() -> None:
    op.drop_table("registration_schedule")
