"""Initial application schema."""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "part",
        sa.Column("part_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.UniqueConstraint("name", name="uq_part_name"),
    )
    op.create_table(
        "module",
        sa.Column("module_id", sa.Integer(), primary_key=True),
        sa.Column("part_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["part_id"], ["part.part_id"], name="fk_module_part_id_part"),
        sa.UniqueConstraint("part_id", "name", name="uq_module_part_id"),
    )
    op.create_table(
        "member",
        sa.Column("member_id", sa.Integer(), primary_key=True),
        sa.Column("login_id", sa.String(100), nullable=False),
        sa.Column("employee_no", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("host_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("apply_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("admin_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_ip", sa.String(64)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["module_id"], ["module.module_id"], name="fk_member_module_id_module"),
        sa.UniqueConstraint("login_id", name="uq_member_login_id"),
        sa.UniqueConstraint("employee_no", name="uq_member_employee_no"),
    )
    op.create_index("ix_member_module_id", "member", ["module_id"])
    op.create_table(
        "login_history",
        sa.Column("login_history_id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer()),
        sa.Column("login_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("login_ip", sa.String(64), nullable=False),
        sa.Column("ip_changed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("login_result", sa.String(40), nullable=False),
        sa.CheckConstraint("login_result IN ('SUCCESS', 'SUCCESS_AFTER_IP_CONFIRM', 'FAILED')", name="ck_login_history_login_result"),
        sa.ForeignKeyConstraint(["member_id"], ["member.member_id"], name="fk_login_history_member_id_member"),
    )
    op.create_table(
        "meeting",
        sa.Column("meeting_id", sa.Integer(), primary_key=True),
        sa.Column("place_name", sa.String(200), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description_content", sa.Text(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("capacity > 0", name="ck_meeting_capacity_positive"),
        sa.CheckConstraint("end_at > start_at", name="ck_meeting_valid_time_range"),
        sa.CheckConstraint("status IN ('DRAFT', 'OPEN', 'CLOSED', 'CANCELLED')", name="ck_meeting_status"),
    )
    op.create_index("ix_meeting_status", "meeting", ["status"])
    op.create_table(
        "meeting_host",
        sa.Column("meeting_id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meeting.meeting_id"], name="fk_meeting_host_meeting_id_meeting"),
        sa.ForeignKeyConstraint(["member_id"], ["member.member_id"], name="fk_meeting_host_member_id_member"),
    )
    op.create_index("ix_meeting_host_member_id", "meeting_host", ["member_id"])
    op.create_table(
        "registration",
        sa.Column("registration_id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["member_id"], ["member.member_id"], name="fk_registration_member_id_member"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meeting.meeting_id"], name="fk_registration_meeting_id_meeting"),
        sa.UniqueConstraint("member_id", name="uq_registration_member_id"),
    )
    op.create_index("ix_registration_meeting_id", "registration", ["meeting_id"])
    op.create_table(
        "registration_history",
        sa.Column("history_id", sa.Integer(), primary_key=True),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("action IN ('APPLY', 'CANCEL')", name="ck_registration_history_action"),
        sa.ForeignKeyConstraint(["member_id"], ["member.member_id"], name="fk_registration_history_member_id_member"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meeting.meeting_id"], name="fk_registration_history_meeting_id_meeting"),
    )


def downgrade() -> None:
    op.drop_table("registration_history")
    op.drop_index("ix_registration_meeting_id", table_name="registration")
    op.drop_table("registration")
    op.drop_index("ix_meeting_host_member_id", table_name="meeting_host")
    op.drop_table("meeting_host")
    op.drop_index("ix_meeting_status", table_name="meeting")
    op.drop_table("meeting")
    op.drop_table("login_history")
    op.drop_index("ix_member_module_id", table_name="member")
    op.drop_table("member")
    op.drop_table("module")
    op.drop_table("part")
