from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Meeting, MeetingHost, Member, Module


async def current_member(request: Request, db: AsyncSession) -> Member:
    member_id = request.session.get("member_id")
    if not member_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    member = await db.scalar(
        select(Member)
        .options(joinedload(Member.module).joinedload(Module.part))
        .where(Member.member_id == member_id, Member.active.is_(True))
    )
    if member is None:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return member


async def require_admin_role(request: Request, db: AsyncSession) -> Member:
    member = await current_member(request, db)
    if not member.admin_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return member


async def require_admin_console(request: Request, db: AsyncSession) -> Member:
    member = await require_admin_role(request, db)
    if not request.session.get("admin_console_verified"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return member


async def require_hosted_meeting(
    db: AsyncSession, member_id: int, meeting_id: int
) -> Meeting:
    meeting = await db.scalar(
        select(Meeting)
        .join(MeetingHost, MeetingHost.meeting_id == Meeting.meeting_id)
        .where(
            Meeting.meeting_id == meeting_id,
            MeetingHost.member_id == member_id,
        )
    )
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return meeting
