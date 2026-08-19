from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models import Meeting, MeetingHost, Member, Module, Registration
from app.policies.access import current_member, require_hosted_meeting
from app.services.meeting_service import (
    MeetingValidationError,
    parse_meeting_details,
    update_meeting_details,
)
from app.services.meeting_view import KOREAN_WEEKDAYS, korean_time, load_applicants
from app.services.session_service import csrf_token, verify_csrf


router = APIRouter(prefix="/host", tags=["host"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
templates.env.filters["korean_time"] = korean_time


@router.get("", response_class=HTMLResponse)
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
    applicants = await load_applicants(
        db, [meeting.meeting_id for meeting in hosted]
    )
    seoul = ZoneInfo("Asia/Seoul")
    meeting_views = [
        {
            "meeting": meeting,
            "start_at": meeting.start_at.astimezone(seoul),
            "weekday": KOREAN_WEEKDAYS[
                meeting.start_at.astimezone(seoul).weekday()
            ],
            "applied_count": len(applicants[meeting.meeting_id]),
            "remaining_count": max(
                meeting.capacity - len(applicants[meeting.meeting_id]), 0
            ),
            "applicants": applicants[meeting.meeting_id],
        }
        for meeting in hosted
    ]
    return templates.TemplateResponse(
        request=request,
        name="host/index.html",
        context={
            "member": member,
            "meeting_views": meeting_views,
            "csrf_token": csrf_token(request),
            "flash": request.session.pop("flash", None),
        },
    )


async def host_meeting_form_context(
    request: Request,
    db: AsyncSession,
    member: Member,
    target: Meeting,
    error: str | None = None,
) -> dict[str, object]:
    applied_count = await db.scalar(
        select(func.count())
        .select_from(Registration)
        .where(Registration.meeting_id == target.meeting_id)
    )
    return {
        "request": request,
        "member": member,
        "target": target,
        "applied_count": applied_count or 0,
        "is_admin_form": False,
        "form_title": "모임 수정",
        "back_url": "/host",
        "back_label": "내가 맡은 모임으로",
        "csrf_token": csrf_token(request),
        "error": error,
        "seoul": ZoneInfo("Asia/Seoul"),
    }


@router.get("/meetings/{meeting_id}/edit", response_class=HTMLResponse)
async def host_meeting_edit_page(
    meeting_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    member = await current_member(request, db)
    target = await require_hosted_meeting(db, member.member_id, meeting_id)
    return templates.TemplateResponse(
        request=request,
        name="meetings/meeting_form.html",
        context=await host_meeting_form_context(request, db, member, target),
    )


@router.post("/meetings/{meeting_id}/edit", response_class=HTMLResponse)
async def host_meeting_edit(
    meeting_id: int,
    request: Request,
    place_name: str = Form(...),
    place_url: str = Form(""),
    neighborhood: str = Form(...),
    representative_menu: str = Form(...),
    host_message: str = Form(...),
    start_at: str = Form(...),
    capacity: int = Form(...),
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    verify_csrf(request, csrf)
    member = await current_member(request, db)
    target = await require_hosted_meeting(db, member.member_id, meeting_id)
    try:
        details = parse_meeting_details(
            place_name=place_name,
            place_url=place_url,
            neighborhood=neighborhood,
            representative_menu=representative_menu,
            host_message=host_message,
            start_at=start_at,
            capacity=capacity,
        )
        await update_meeting_details(db, target, details)
        await db.commit()
    except MeetingValidationError as exc:
        await db.rollback()
        target = await require_hosted_meeting(db, member.member_id, meeting_id)
        return templates.TemplateResponse(
            request=request,
            name="meetings/meeting_form.html",
            context=await host_meeting_form_context(
                request, db, member, target, str(exc)
            ),
            status_code=422,
        )
    request.session["flash"] = ("success", "모임 정보를 수정했습니다.")
    return RedirectResponse("/host", status_code=303)


@router.get("/meetings/{meeting_id}/registrations", response_class=HTMLResponse)
async def host_meeting_registrations(
    meeting_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    member = await current_member(request, db)
    meeting = await require_hosted_meeting(db, member.member_id, meeting_id)
    applicants = (
        await db.scalars(
            select(Member)
            .join(Registration, Registration.member_id == Member.member_id)
            .options(joinedload(Member.module).joinedload(Module.part))
            .where(Registration.meeting_id == meeting_id)
            .order_by(Registration.registered_at, Member.member_id)
        )
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="host/registrations.html",
        context={
            "member": member,
            "meeting": meeting,
            "applicants": applicants,
            "seoul": ZoneInfo("Asia/Seoul"),
            "weekdays": KOREAN_WEEKDAYS,
            "csrf_token": csrf_token(request),
        },
    )
