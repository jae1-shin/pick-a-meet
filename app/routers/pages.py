from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Meeting, MeetingHost, Member, Module, Part, Registration
from app.services.session_service import csrf_token


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


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


@router.get("/meetings", response_class=HTMLResponse)
async def meetings_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    try:
        member = await current_member(request, db)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)

    count_subquery = (
        select(Registration.meeting_id, func.count().label("applied_count"))
        .group_by(Registration.meeting_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Meeting, func.coalesce(count_subquery.c.applied_count, 0))
            .outerjoin(count_subquery, count_subquery.c.meeting_id == Meeting.meeting_id)
            .where(Meeting.status == "OPEN")
            .order_by(Meeting.start_at)
        )
    ).all()
    meeting_views = [
        {
            "meeting": meeting,
            "applied_count": applied_count,
            "remaining_count": max(meeting.capacity - applied_count, 0),
        }
        for meeting, applied_count in rows
    ]
    return templates.TemplateResponse(
        request=request,
        name="meetings/list.html",
        context={
            "member": member,
            "meetings": meeting_views,
            "csrf_token": csrf_token(request),
        },
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    member = await current_member(request, db)
    if not member.admin_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    members = (
        await db.scalars(
            select(Member)
            .options(joinedload(Member.module).joinedload(Module.part))
            .order_by(Member.member_id)
        )
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={"member": member, "members": members, "csrf_token": csrf_token(request)},
    )


@router.get("/host", response_class=HTMLResponse)
async def host_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    member = await current_member(request, db)
    hosted = (
        await db.scalars(
            select(Meeting)
            .join(MeetingHost, MeetingHost.meeting_id == Meeting.meeting_id)
            .where(MeetingHost.member_id == member.member_id)
            .order_by(Meeting.start_at)
        )
    ).all()
    if not hosted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return templates.TemplateResponse(
        request=request,
        name="host/index.html",
        context={"member": member, "meetings": hosted, "csrf_token": csrf_token(request)},
    )
