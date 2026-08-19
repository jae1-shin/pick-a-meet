from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Meeting,
    MeetingHost,
    Member,
    Module,
    Registration,
    RegistrationHistory,
)
from app.services.part_registration_policy import part_registration_allowed
from app.services.registration_window import registration_is_open


async def _part_rule_allows_registration(
    db: AsyncSession,
    member: Member,
    meeting_id: int,
) -> bool:
    candidate_part_id = await db.scalar(
        select(Module.part_id).where(Module.module_id == member.module_id)
    )
    if candidate_part_id is None:
        return False

    active_part_member_count = await db.scalar(
        select(func.count())
        .select_from(Member)
        .join(Module, Module.module_id == Member.module_id)
        .where(
            Module.part_id == candidate_part_id,
            Member.active.is_(True),
        )
    )
    distribution_meeting_count = await db.scalar(
        select(func.count())
        .select_from(Meeting)
        .where(Meeting.status.in_(("OPEN", "CLOSED")))
    )
    applicant_part_ids = (
        await db.scalars(
            select(Module.part_id)
            .select_from(Registration)
            .join(Member, Member.member_id == Registration.member_id)
            .join(Module, Module.module_id == Member.module_id)
            .where(Registration.meeting_id == meeting_id)
        )
    ).all()
    return part_registration_allowed(
        candidate_part_id=candidate_part_id,
        applicant_part_ids=applicant_part_ids,
        active_part_member_count=active_part_member_count or 0,
        distribution_meeting_count=distribution_meeting_count or 0,
    )


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
            if not await _part_rule_allows_registration(db, member, meeting_id):
                return "PART_LIMIT_REACHED"

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
