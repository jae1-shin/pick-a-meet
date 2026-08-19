from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Part(Base):
    __tablename__ = "part"

    part_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    modules: Mapped[list["Module"]] = relationship(back_populates="part")


class Module(Base):
    __tablename__ = "module"
    __table_args__ = (UniqueConstraint("part_id", "name"),)

    module_id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("part.part_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    part: Mapped[Part] = relationship(back_populates="modules")
    members: Mapped[list["Member"]] = relationship(back_populates="module")


class Member(TimestampMixin, Base):
    __tablename__ = "member"

    member_id: Mapped[int] = mapped_column(primary_key=True)
    login_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    employee_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    module_id: Mapped[int] = mapped_column(
        ForeignKey("module.module_id"), nullable=False, index=True
    )
    host_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    apply_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    admin_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_ip: Mapped[str | None] = mapped_column(String(64))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    module: Mapped[Module] = relationship(back_populates="members")


class LoginHistory(Base):
    __tablename__ = "login_history"
    __table_args__ = (
        CheckConstraint(
            "login_result IN ('SUCCESS', 'SUCCESS_AFTER_IP_CONFIRM', 'FAILED')",
            name="login_result",
        ),
    )

    login_history_id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("member.member_id"))
    login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    login_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    login_result: Mapped[str] = mapped_column(String(40), nullable=False)


class Meeting(TimestampMixin, Base):
    __tablename__ = "meeting"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="capacity_positive"),
        CheckConstraint("end_at > start_at", name="valid_time_range"),
        CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'CLOSED', 'CANCELLED')",
            name="status",
        ),
        Index("ix_meeting_status", "status"),
    )

    meeting_id: Mapped[int] = mapped_column(primary_key=True)
    place_name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description_content: Mapped[str] = mapped_column(Text, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=False)


class MeetingHost(Base):
    __tablename__ = "meeting_host"

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meeting.meeting_id"), primary_key=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.member_id"), nullable=False, index=True
    )


class Registration(Base):
    __tablename__ = "registration"
    __table_args__ = (Index("ix_registration_meeting_id", "meeting_id"),)

    registration_id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("member.member_id"), unique=True, nullable=False
    )
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meeting.meeting_id"), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RegistrationHistory(Base):
    __tablename__ = "registration_history"
    __table_args__ = (
        CheckConstraint("action IN ('APPLY', 'CANCEL')", name="action"),
    )

    history_id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("member.member_id"), nullable=False)
    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meeting.meeting_id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
