"""Remove meeting end time."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0003"
down_revision = "20260819_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_meeting_valid_time_range", "meeting", type_="check")
    op.drop_column("meeting", "end_at")


def downgrade() -> None:
    op.add_column(
        "meeting",
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE meeting SET end_at = start_at + interval '2 hours'")
    op.alter_column("meeting", "end_at", nullable=False)
    op.create_check_constraint(
        "ck_meeting_valid_time_range", "meeting", "end_at > start_at"
    )
