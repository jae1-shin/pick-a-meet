"""Add structured meeting content fields."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0002"
down_revision = "20260819_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meeting", sa.Column("place_url", sa.String(500)))
    op.add_column(
        "meeting",
        sa.Column(
            "neighborhood",
            sa.String(100),
            nullable=False,
            server_default="미지정",
        ),
    )
    op.add_column(
        "meeting",
        sa.Column(
            "representative_menu",
            sa.String(200),
            nullable=False,
            server_default="미정",
        ),
    )
    op.add_column(
        "meeting",
        sa.Column(
            "host_message",
            sa.Text(),
            nullable=False,
            server_default="함께 즐거운 시간 보내요!",
        ),
    )
    op.alter_column("meeting", "neighborhood", server_default=None)
    op.alter_column("meeting", "representative_menu", server_default=None)
    op.alter_column("meeting", "host_message", server_default=None)


def downgrade() -> None:
    op.drop_column("meeting", "host_message")
    op.drop_column("meeting", "representative_menu")
    op.drop_column("meeting", "neighborhood")
    op.drop_column("meeting", "place_url")
