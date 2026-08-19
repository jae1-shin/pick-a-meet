from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.policies.access import current_member
from app.services.meeting_view import (
    KOREAN_WEEKDAYS,
    build_meeting_filter_context,
    korean_time,
    load_public_meeting_views,
)
from app.services.registration_service import apply_to_meeting, cancel_registration
from app.services.registration_window import (
    registration_is_open,
    registration_opens_at,
    registration_remaining_ms,
)
from app.services.session_service import csrf_token, verify_csrf


router = APIRouter(tags=["meetings"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
templates.env.filters["korean_time"] = korean_time
settings = get_settings()


@router.get("/registration-window/status")
async def registration_window_status(request: Request) -> dict[str, object]:
    if not request.session.get("member_id"):
        raise HTTPException(status_code=401)
    return {
        "open": registration_is_open(),
        "remaining_ms": registration_remaining_ms(),
    }


@router.get("/waiting", response_class=HTMLResponse)
async def waiting_page(
    request: Request,
    neighborhood_filters: list[str] | None = Query(None, alias="neighborhood"),
    date_filters: list[str] | None = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    try:
        member = await current_member(request, db)
    except HTTPException:
        return RedirectResponse("/login", status_code=303)
    if member.admin_enabled or member.host_enabled or registration_is_open():
        return RedirectResponse("/meetings", status_code=303)
    opens_at = registration_opens_at()
    if opens_at is None:
        return RedirectResponse("/meetings", status_code=303)
    remaining_ms = registration_remaining_ms()
    local_opens_at = opens_at.astimezone(ZoneInfo("Asia/Seoul"))
    meeting_views, _ = await load_public_meeting_views(
        db, member, registration_open=False
    )
    filter_context = build_meeting_filter_context(
        meeting_views,
        neighborhood_filters=neighborhood_filters,
        date_filters=date_filters,
        base_path="/waiting",
    )
    return templates.TemplateResponse(
        request=request,
        name="meetings/waiting.html",
        context={
            "member": member,
            "csrf_token": csrf_token(request),
            "opens_at": local_opens_at,
            "weekday": KOREAN_WEEKDAYS[local_opens_at.weekday()],
            "remaining_ms": remaining_ms,
            **filter_context,
        },
    )


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


async def _meeting_list_context(
    request: Request,
    member,
    db: AsyncSession,
    *,
    group_by: str = Query("all", pattern="^(all|neighborhood|date)$"),
    neighborhood_filters: list[str] | None = Query(None, alias="neighborhood"),
    date_filters: list[str] | None = Query(None, alias="date"),
) -> dict[str, object]:
    registration_open = registration_is_open()
    meeting_views, is_open_host = await load_public_meeting_views(
        db, member, registration_open=registration_open
    )
    filter_context = build_meeting_filter_context(
        meeting_views,
        neighborhood_filters=neighborhood_filters,
        date_filters=date_filters,
        base_path="/meetings",
        base_params=[("group_by", group_by)],
    )
    meeting_views = filter_context["meeting_views"]
    preserved_filter_params = filter_context["preserved_filter_params"]
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
    refresh_params = [("group_by", group_by)] + preserved_filter_params
    return {
        "member": member,
        "groups": groups,
        "group_by": group_by,
        **filter_context,
        "view_hrefs": view_hrefs,
        "csrf_token": csrf_token(request),
        "is_open_host": is_open_host,
        "registration_open": registration_open,
        "meeting_refresh_href": "/meetings/status-fragment?"
        + urlencode(refresh_params),
        "polling_interval_ms": settings.polling_interval_seconds * 1000,
    }


@router.get("/meetings", response_class=HTMLResponse)
async def meetings_page(
    request: Request,
    group_by: str = Query("all", pattern="^(all|neighborhood|date)$"),
    neighborhood_filters: list[str] | None = Query(None, alias="neighborhood"),
    date_filters: list[str] | None = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if not request.session.get("member_id"):
        return RedirectResponse("/login", status_code=303)
    member = await current_member(request, db)
    if not registration_is_open() and not (
        member.admin_enabled or member.host_enabled
    ):
        return RedirectResponse("/waiting", status_code=303)
    context = await _meeting_list_context(
        request,
        member,
        db,
        group_by=group_by,
        neighborhood_filters=neighborhood_filters,
        date_filters=date_filters,
    )
    context["flash"] = request.session.pop("flash", None)
    return templates.TemplateResponse(
        request=request,
        name="meetings/list.html",
        context=context,
    )


@router.get("/meetings/status-fragment", response_class=HTMLResponse)
async def meetings_status_fragment(
    request: Request,
    group_by: str = Query("all", pattern="^(all|neighborhood|date)$"),
    neighborhood_filters: list[str] | None = Query(None, alias="neighborhood"),
    date_filters: list[str] | None = Query(None, alias="date"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if not request.session.get("member_id"):
        raise HTTPException(status_code=401)
    member = await current_member(request, db)
    if not registration_is_open() and not (
        member.admin_enabled or member.host_enabled
    ):
        raise HTTPException(status_code=409)
    context = await _meeting_list_context(
        request,
        member,
        db,
        group_by=group_by,
        neighborhood_filters=neighborhood_filters,
        date_filters=date_filters,
    )
    response = templates.TemplateResponse(
        request=request,
        name="meetings/_groups.html",
        context=context,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


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
    if result == "REGISTRATION_NOT_STARTED":
        return RedirectResponse("/waiting", status_code=303)
    messages = {
        "APPLIED": ("success", "신청이 완료되었습니다."),
        "NOT_ELIGIBLE": ("danger", "신청 가능한 사용자가 아닙니다."),
        "HOST_NOT_ALLOWED": ("danger", "현재 모임 Host는 신청할 수 없습니다."),
        "ALREADY_REGISTERED": ("danger", "이미 다른 모임을 신청했습니다."),
        "MEETING_NOT_OPEN": ("danger", "신청 가능한 모임이 아닙니다."),
        "MEETING_FULL": ("danger", "방금 모집이 마감되었습니다."),
        "PART_LIMIT_REACHED": (
            "danger",
            "같은 파트 신청 인원 제한으로 신청할 수 없습니다.",
        ),
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
    if result == "REGISTRATION_NOT_STARTED":
        return RedirectResponse("/waiting", status_code=303)
    messages = {
        "CANCELLED": ("success", "신청을 취소했습니다."),
        "NOT_REGISTERED": ("danger", "취소할 신청이 없습니다."),
        "NOT_ELIGIBLE": ("danger", "신청 가능한 사용자가 아닙니다."),
        "MEETING_NOT_OPEN": ("danger", "신청 기간에는 변경할 수 없습니다."),
    }
    request.session["flash"] = messages[result]
    return RedirectResponse("/meetings", status_code=303)
