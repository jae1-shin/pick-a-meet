from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Member, Module, Registration


KOREAN_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def korean_time(value) -> str:
    period = "오전" if value.hour < 12 else "오후"
    hour = value.hour % 12 or 12
    return f"{period} {hour}:{value.strftime('%M')}"


async def load_applicants(
    db: AsyncSession, meeting_ids: list[int]
) -> dict[int, list[Member]]:
    applicants: dict[int, list[Member]] = {meeting_id: [] for meeting_id in meeting_ids}
    if not meeting_ids:
        return applicants
    rows = (
        await db.execute(
            select(Registration.meeting_id, Member)
            .join(Member, Member.member_id == Registration.member_id)
            .options(joinedload(Member.module).joinedload(Module.part))
            .where(Registration.meeting_id.in_(meeting_ids))
            .order_by(Registration.meeting_id, Registration.registered_at)
        )
    ).all()
    for meeting_id, applicant in rows:
        applicants[meeting_id].append(applicant)
    return applicants
