from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Meeting,
    MeetingHost,
    Member,
    Registration,
    RegistrationHistory,
)
from app.services.registration_window import registration_is_open


async def apply_to_meeting(
    db: AsyncSession, member_id: int, meeting_id: int
) -> str:
    if not registration_is_open():
        return "REGISTRATION_NOT_STARTED"
    try:
        async with db.begin():
            member = await db.scalar(
                select(Member)
                .where(Member.member_id == member_id)
                .with_for_update()
            )
            if member is None or not member.active or not member.apply_enabled:
                return "NOT_ELIGIBLE"

            is_open_host = await db.scalar(
                select(func.count())
                .select_from(MeetingHost)
                .join(Meeting, Meeting.meeting_id == MeetingHost.meeting_id)
                .where(
                    MeetingHost.member_id == member_id,
                    Meeting.status == "OPEN",
                )
            )
            if is_open_host:
                return "HOST_NOT_ALLOWED"

            existing = await db.scalar(
                select(Registration).where(Registration.member_id == member_id)
            )
            if existing is not None:
                return "ALREADY_REGISTERED"

            meeting = await db.scalar(
                select(Meeting)
                .where(Meeting.meeting_id == meeting_id)
                .with_for_update()
            )
            if meeting is None or meeting.status != "OPEN":
                return "MEETING_NOT_OPEN"

            applied_count = await db.scalar(
                select(func.count())
                .select_from(Registration)
                .where(Registration.meeting_id == meeting_id)
            )
            if (applied_count or 0) >= meeting.capacity:
                return "MEETING_FULL"

            db.add(Registration(member_id=member_id, meeting_id=meeting_id))
            db.add(
                RegistrationHistory(
                    member_id=member_id,
                    meeting_id=meeting_id,
                    action="APPLY",
                )
            )
        return "APPLIED"
    except IntegrityError:
        await db.rollback()
        return "ALREADY_REGISTERED"


async def cancel_registration(db: AsyncSession, member_id: int) -> str:
    if not registration_is_open():
        return "REGISTRATION_NOT_STARTED"
    async with db.begin():
        member = await db.scalar(
            select(Member).where(Member.member_id == member_id).with_for_update()
        )
        if member is None or not member.active:
            return "NOT_ELIGIBLE"
        registration = await db.scalar(
            select(Registration)
            .where(Registration.member_id == member_id)
            .with_for_update()
        )
        if registration is None:
            return "NOT_REGISTERED"
        meeting = await db.get(Meeting, registration.meeting_id)
        if meeting is None or meeting.status != "OPEN":
            return "MEETING_NOT_OPEN"
        meeting_id = registration.meeting_id
        await db.delete(registration)
        db.add(
            RegistrationHistory(
                member_id=member_id,
                meeting_id=meeting_id,
                action="CANCEL",
            )
        )
    return "CANCELLED"
