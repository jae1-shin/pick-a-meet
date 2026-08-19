from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Meeting, MeetingHost, Registration
from app.policies.access import current_member
from app.services.meeting_view import KOREAN_WEEKDAYS, korean_time, load_applicants
from app.services.registration_service import apply_to_meeting, cancel_registration
from app.services.session_service import csrf_token, verify_csrf


router = APIRouter(tags=["meetings"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
templates.env.filters["korean_time"] = korean_time


@router.get("/style/font-preview", response_class=HTMLResponse)
async def font_preview_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="style/font_preview.html",
        context={
            "font_options": (
                {
                    "key": "A",
                    "name": "Noto Sans KR",
                    "class_name": "font-noto",
                    "note": "단정하고 중립적이라 가장 안정적인 기본안",
                },
                {
                    "key": "B",
                    "name": "IBM Plex Sans KR",
                    "class_name": "font-ibm",
                    "note": "숫자와 관리 테이블이 또렷한 실무형",
                },
                {
                    "key": "C",
                    "name": "Gowun Dodum",
                    "class_name": "font-gowun",
                    "note": "모임 서비스에 어울리는 부드럽고 친근한 인상",
                },
                {
                    "key": "D",
                    "name": "Nanum Gothic",
                    "class_name": "font-nanum",
                    "note": "익숙하고 편안한 사내 서비스 느낌",
                },
            )
        },
    )


@router.get("/meetings", response_class=HTMLResponse)
async def meetings_page(
    request: Request,
    group_by: str = Query("all", pattern="^(all|neighborhood|date)$"),
    neighborhood_filters: list[str] | None = Query(None, alias="neighborhood"),
    date_filters: list[str] | None = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
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
    active_registration = await db.scalar(
        select(Registration).where(Registration.member_id == member.member_id)
    )
    is_open_host = bool(
        await db.scalar(
            select(func.count())
            .select_from(MeetingHost)
            .join(Meeting, Meeting.meeting_id == MeetingHost.meeting_id)
            .where(
                MeetingHost.member_id == member.member_id,
                Meeting.status == "OPEN",
            )
        )
    )
    seoul = ZoneInfo("Asia/Seoul")
    applicants = await load_applicants(
        db, [meeting.meeting_id for meeting, _ in rows]
    )
    meeting_views = [
        {
            "meeting": meeting,
            "applied_count": applied_count,
            "remaining_count": max(meeting.capacity - applied_count, 0),
            "start_at": meeting.start_at.astimezone(seoul),
            "weekday": KOREAN_WEEKDAYS[meeting.start_at.astimezone(seoul).weekday()],
            "is_registered": bool(
                active_registration
                and active_registration.meeting_id == meeting.meeting_id
            ),
            "can_apply": bool(
                member.apply_enabled
                and not is_open_host
                and active_registration is None
                and applied_count < meeting.capacity
            ),
            "applicants": applicants[meeting.meeting_id],
        }
        for meeting, applied_count in rows
    ]
    neighborhood_options = [
        {"value": value, "label": value}
        for value in sorted(
            {item["meeting"].neighborhood for item in meeting_views}
        )
    ]
    date_options = [
        {
            "value": value,
            "label": f"{start.strftime('%m.%d')} ({KOREAN_WEEKDAYS[start.weekday()]})",
        }
        for value, start in sorted(
            {
                item["start_at"].date().isoformat(): item["start_at"]
                for item in meeting_views
            }.items()
        )
    ]
    valid_neighborhoods = {option["value"] for option in neighborhood_options}
    selected_neighborhoods = {
        value
        for value in (neighborhood_filters or [])
        if len(value) <= 100 and value in valid_neighborhoods
    }
    valid_dates = {option["value"] for option in date_options}
    selected_dates = {
        value
        for value in (date_filters or [])
        if len(value) <= 100 and value in valid_dates
    }
    selected_neighborhoods_in_order = [
        option["value"]
        for option in neighborhood_options
        if option["value"] in selected_neighborhoods
    ]
    selected_dates_in_order = [
        option["value"]
        for option in date_options
        if option["value"] in selected_dates
    ]
    if selected_neighborhoods:
        meeting_views = [
            item
            for item in meeting_views
            if item["meeting"].neighborhood in selected_neighborhoods
        ]
    if selected_dates:
        meeting_views = [
            item
            for item in meeting_views
            if item["start_at"].date().isoformat() in selected_dates
        ]

    for option in neighborhood_options:
        value = option["value"]
        toggled = [
            selected
            for selected in selected_neighborhoods_in_order
            if selected != value
        ]
        if value not in selected_neighborhoods:
            toggled.append(value)
        option["selected"] = value in selected_neighborhoods
        option["href"] = "/meetings?" + urlencode(
            [("group_by", group_by)]
            + [("neighborhood", selected) for selected in toggled]
            + [("date", selected) for selected in selected_dates_in_order]
        )

    for option in date_options:
        value = option["value"]
        toggled = [
            selected for selected in selected_dates_in_order if selected != value
        ]
        if value not in selected_dates:
            toggled.append(value)
        option["selected"] = value in selected_dates
        option["href"] = "/meetings?" + urlencode(
            [("group_by", group_by)]
            + [
                ("neighborhood", selected)
                for selected in selected_neighborhoods_in_order
            ]
            + [("date", selected) for selected in toggled]
        )

    preserved_filter_params = [
        ("neighborhood", selected)
        for selected in selected_neighborhoods_in_order
    ] + [("date", selected) for selected in selected_dates_in_order]
    neighborhood_clear_href = "/meetings?" + urlencode(
        [("group_by", group_by)]
        + [("date", selected) for selected in selected_dates_in_order]
    )
    date_clear_href = "/meetings?" + urlencode(
        [("group_by", group_by)]
        + [
            ("neighborhood", selected)
            for selected in selected_neighborhoods_in_order
        ]
    )
    view_hrefs = {
        view: "/meetings?" + urlencode(
            [("group_by", view)] + preserved_filter_params
        )
        for view in ("all", "neighborhood", "date")
    }

    if group_by == "date":
        meeting_views.sort(
            key=lambda item: (
                item["start_at"].date(),
                item["meeting"].neighborhood,
                item["start_at"],
            )
        )
        group_key = lambda item: item["start_at"].date().isoformat()
        group_title = lambda item: (
            f"{item['start_at'].strftime('%Y년 %m월 %d일')} ({item['weekday']})"
        )
    elif group_by == "neighborhood":
        meeting_views.sort(
            key=lambda item: (item["meeting"].neighborhood, item["start_at"])
        )
        group_key = lambda item: item["meeting"].neighborhood
        group_title = lambda item: item["meeting"].neighborhood
    else:
        meeting_views.sort(
            key=lambda item: (item["start_at"], item["meeting"].neighborhood)
        )
        group_key = lambda item: "all"
        group_title = lambda item: None

    groups: list[dict[str, object]] = []
    for item in meeting_views:
        key = group_key(item)
        if not groups or groups[-1]["key"] != key:
            groups.append({"key": key, "title": group_title(item), "items": []})
        groups[-1]["items"].append(item)
    return templates.TemplateResponse(
        request=request,
        name="meetings/list.html",
        context={
            "member": member,
            "groups": groups,
            "group_by": group_by,
            "selected_neighborhoods": selected_neighborhoods_in_order,
            "selected_dates": selected_dates_in_order,
            "neighborhood_clear_href": neighborhood_clear_href,
            "date_clear_href": date_clear_href,
            "neighborhood_options": neighborhood_options,
            "date_options": date_options,
            "view_hrefs": view_hrefs,
            "csrf_token": csrf_token(request),
            "flash": request.session.pop("flash", None),
            "is_open_host": is_open_host,
        },
    )


@router.post("/meetings/{meeting_id}/apply")
async def apply(
    meeting_id: int,
    request: Request,
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    verify_csrf(request, csrf)
    member_id = request.session.get("member_id")
    if not member_id:
        return RedirectResponse("/login", status_code=303)
    result = await apply_to_meeting(db, member_id, meeting_id)
    messages = {
        "APPLIED": ("success", "신청이 완료되었습니다."),
        "NOT_ELIGIBLE": ("danger", "신청 가능한 사용자가 아닙니다."),
        "HOST_NOT_ALLOWED": ("danger", "현재 모임 Host는 신청할 수 없습니다."),
        "ALREADY_REGISTERED": ("danger", "이미 다른 모임을 신청했습니다."),
        "MEETING_NOT_OPEN": ("danger", "신청 가능한 모임이 아닙니다."),
        "MEETING_FULL": ("danger", "방금 모집이 마감되었습니다."),
    }
    request.session["flash"] = messages[result]
    return RedirectResponse("/meetings", status_code=303)


@router.post("/registrations/cancel")
async def cancel(
    request: Request,
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    verify_csrf(request, csrf)
    member_id = request.session.get("member_id")
    if not member_id:
        return RedirectResponse("/login", status_code=303)
    result = await cancel_registration(db, member_id)
    request.session["flash"] = (
        ("success", "신청을 취소했습니다.")
        if result == "CANCELLED"
        else ("danger", "취소할 신청이 없습니다.")
    )
    return RedirectResponse("/meetings", status_code=303)
