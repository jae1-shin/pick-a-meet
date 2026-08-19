import hmac
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.database import get_db
from app.models import Meeting, MeetingHost, Member, Module, Part, Registration
from app.services.session_service import csrf_token, verify_csrf
from app.services.registration_service import apply_to_meeting, cancel_registration


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
settings = get_settings()
KOREAN_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


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


async def require_admin(request: Request, db: AsyncSession) -> Member:
    member = await current_member(request, db)
    if not member.admin_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if not request.session.get("admin_console_verified"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return member


async def get_or_create_module(db: AsyncSession, part_name: str, module_name: str) -> Module:
    clean_part = part_name.strip()
    clean_module = module_name.strip()
    part = await db.scalar(select(Part).where(Part.name == clean_part))
    if part is None:
        part = Part(name=clean_part)
        db.add(part)
        await db.flush()
    module = await db.scalar(
        select(Module).where(Module.part_id == part.part_id, Module.name == clean_module)
    )
    if module is None:
        module = Module(part_id=part.part_id, name=clean_module)
        db.add(module)
        await db.flush()
    return module


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


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    sort: str = Query("name", max_length=30),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    member = await current_member(request, db)
    if not member.admin_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if not request.session.get("admin_console_verified"):
        return RedirectResponse("/admin/unlock", status_code=303)
    sort_columns = {
        "name": Member.name,
        "login_id": Member.login_id,
        "employee_no": Member.employee_no,
        "part": Part.name,
        "module": Module.name,
        "apply": Member.apply_enabled,
        "host": Member.host_enabled,
        "admin": Member.admin_enabled,
        "active": Member.active,
    }
    if sort not in sort_columns:
        sort = "name"
    direction = sort_columns[sort].desc() if order == "desc" else sort_columns[sort].asc()
    members = (
        await db.scalars(
            select(Member)
            .join(Module, Module.module_id == Member.module_id)
            .join(Part, Part.part_id == Module.part_id)
            .options(joinedload(Member.module).joinedload(Module.part))
            .order_by(direction, Member.member_id)
        )
    ).all()
    sort_links = {
        key: {
            "href": "/admin?" + urlencode(
                {
                    "sort": key,
                    "order": "desc" if sort == key and order == "asc" else "asc",
                }
            ),
            "direction": order if sort == key else None,
        }
        for key in sort_columns
    }
    return templates.TemplateResponse(
        request=request,
        name="admin/index.html",
        context={
            "member": member,
            "members": members,
            "csrf_token": csrf_token(request),
            "sort_links": sort_links,
        },
    )


@router.get("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    member = await current_member(request, db)
    if not member.admin_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if request.session.get("admin_console_verified"):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="admin/unlock.html",
        context={"member": member, "csrf_token": csrf_token(request), "error": None},
    )


@router.post("/admin/unlock", response_class=HTMLResponse)
async def admin_unlock(
    request: Request,
    password: str = Form(...),
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    verify_csrf(request, csrf)
    member = await current_member(request, db)
    if not member.admin_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    expected = settings.admin_console_password.get_secret_value()
    if not hmac.compare_digest(password, expected):
        return templates.TemplateResponse(
            request=request,
            name="admin/unlock.html",
            context={
                "member": member,
                "csrf_token": csrf_token(request),
                "error": "관리자 콘솔 비밀번호를 확인해주세요.",
            },
            status_code=401,
        )
    request.session["admin_console_verified"] = True
    return RedirectResponse("/admin", status_code=303)


def member_form_context(
    request: Request,
    current_admin: Member,
    target: Member | None = None,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "request": request,
        "member": current_admin,
        "target": target,
        "csrf_token": csrf_token(request),
        "error": error,
    }


@router.get("/admin/members/new", response_class=HTMLResponse)
async def admin_member_new_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    admin = await require_admin(request, db)
    return templates.TemplateResponse(
        request=request,
        name="admin/member_form.html",
        context=member_form_context(request, admin),
    )


@router.post("/admin/members/new", response_class=HTMLResponse)
async def admin_member_new(
    request: Request,
    login_id: str = Form(...),
    employee_no: str = Form(...),
    name: str = Form(...),
    part_name: str = Form(...),
    module_name: str = Form(...),
    apply_enabled: bool = Form(False),
    host_enabled: bool = Form(False),
    admin_enabled: bool = Form(False),
    active: bool = Form(False),
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    verify_csrf(request, csrf)
    admin = await require_admin(request, db)
    try:
        module = await get_or_create_module(db, part_name, module_name)
        db.add(
            Member(
                login_id=login_id.strip(),
                employee_no=employee_no.strip(),
                name=name.strip(),
                module_id=module.module_id,
                apply_enabled=apply_enabled,
                host_enabled=host_enabled,
                admin_enabled=admin_enabled,
                active=active,
            )
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="admin/member_form.html",
            context=member_form_context(
                request, admin, error="이미 사용 중인 ID 또는 사번입니다."
            ),
            status_code=409,
        )
    return RedirectResponse("/admin", status_code=303)


@router.get("/admin/members/{member_id}/edit", response_class=HTMLResponse)
async def admin_member_edit_page(
    member_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    admin = await require_admin(request, db)
    target = await db.scalar(
        select(Member)
        .options(joinedload(Member.module).joinedload(Module.part))
        .where(Member.member_id == member_id)
    )
    if target is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="admin/member_form.html",
        context=member_form_context(request, admin, target),
    )


@router.post("/admin/members/{member_id}/edit", response_class=HTMLResponse)
async def admin_member_edit(
    member_id: int,
    request: Request,
    login_id: str = Form(...),
    employee_no: str = Form(...),
    name: str = Form(...),
    part_name: str = Form(...),
    module_name: str = Form(...),
    apply_enabled: bool = Form(False),
    host_enabled: bool = Form(False),
    admin_enabled: bool = Form(False),
    active: bool = Form(False),
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    verify_csrf(request, csrf)
    admin = await require_admin(request, db)
    target = await db.get(Member, member_id)
    if target is None:
        raise HTTPException(status_code=404)
    try:
        module = await get_or_create_module(db, part_name, module_name)
        target.login_id = login_id.strip()
        target.employee_no = employee_no.strip()
        target.name = name.strip()
        target.module_id = module.module_id
        target.apply_enabled = apply_enabled
        target.host_enabled = host_enabled
        target.admin_enabled = admin_enabled
        target.active = active
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="admin/member_form.html",
            context=member_form_context(
                request, admin, target, "이미 사용 중인 ID 또는 사번입니다."
            ),
            status_code=409,
        )
    return RedirectResponse("/admin", status_code=303)


async def meeting_form_context(
    request: Request,
    db: AsyncSession,
    admin: Member,
    target: Meeting | None = None,
    error: str | None = None,
) -> dict[str, object]:
    hosts = (
        await db.scalars(
            select(Member)
            .where(Member.host_enabled.is_(True), Member.active.is_(True))
            .order_by(Member.name)
        )
    ).all()
    host_id = None
    if target is not None:
        host_id = await db.scalar(
            select(MeetingHost.member_id).where(
                MeetingHost.meeting_id == target.meeting_id
            )
        )
    return {
        "request": request,
        "member": admin,
        "target": target,
        "hosts": hosts,
        "host_id": host_id,
        "csrf_token": csrf_token(request),
        "error": error,
        "seoul": ZoneInfo("Asia/Seoul"),
    }


def parse_meeting_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed


def validate_place_url(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if not cleaned.startswith(("https://", "http://")):
        raise ValueError("장소 링크는 http:// 또는 https://로 시작해야 합니다.")
    return cleaned


@router.get("/admin/meetings", response_class=HTMLResponse)
async def admin_meetings_page(
    request: Request,
    sort: str = Query("start_at", max_length=30),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    admin = await require_admin(request, db)
    count_subquery = (
        select(Registration.meeting_id, func.count().label("applied_count"))
        .group_by(Registration.meeting_id)
        .subquery()
    )
    applied_count = func.coalesce(count_subquery.c.applied_count, 0)
    sort_columns = {
        "start_at": Meeting.start_at,
        "neighborhood": Meeting.neighborhood,
        "place": Meeting.place_name,
        "menu": Meeting.representative_menu,
        "host": Member.name,
        "applied": applied_count,
        "capacity": Meeting.capacity,
        "status": Meeting.status,
    }
    if sort not in sort_columns:
        sort = "start_at"
    direction = sort_columns[sort].desc() if order == "desc" else sort_columns[sort].asc()
    rows = (
        await db.execute(
            select(Meeting, Member, applied_count)
            .join(MeetingHost, MeetingHost.meeting_id == Meeting.meeting_id)
            .join(Member, Member.member_id == MeetingHost.member_id)
            .outerjoin(count_subquery, count_subquery.c.meeting_id == Meeting.meeting_id)
            .order_by(direction, Meeting.meeting_id)
        )
    ).all()
    applicants = await load_applicants(
        db, [meeting.meeting_id for meeting, _, _ in rows]
    )
    sort_links = {
        key: {
            "href": "/admin/meetings?" + urlencode(
                {
                    "sort": key,
                    "order": "desc" if sort == key and order == "asc" else "asc",
                }
            ),
            "direction": order if sort == key else None,
        }
        for key in sort_columns
    }
    return templates.TemplateResponse(
        request=request,
        name="admin/meetings.html",
        context={
            "member": admin,
            "rows": rows,
            "seoul": ZoneInfo("Asia/Seoul"),
            "weekdays": KOREAN_WEEKDAYS,
            "applicants": applicants,
            "sort_links": sort_links,
            "csrf_token": csrf_token(request),
        },
    )


@router.get("/admin/meetings/new", response_class=HTMLResponse)
async def admin_meeting_new_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    admin = await require_admin(request, db)
    return templates.TemplateResponse(
        request=request,
        name="admin/meeting_form.html",
        context=await meeting_form_context(request, db, admin),
    )


@router.post("/admin/meetings/new", response_class=HTMLResponse)
async def admin_meeting_new(
    request: Request,
    place_name: str = Form(...),
    place_url: str = Form(""),
    neighborhood: str = Form(...),
    representative_menu: str = Form(...),
    host_message: str = Form(...),
    start_at: str = Form(...),
    capacity: int = Form(...),
    meeting_status: str = Form(...),
    host_id: int = Form(...),
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    verify_csrf(request, csrf)
    admin = await require_admin(request, db)
    try:
        start = parse_meeting_time(start_at)
        if capacity < 1:
            raise ValueError("정원을 확인해주세요.")
        if meeting_status not in {"DRAFT", "OPEN", "CLOSED", "CANCELLED"}:
            raise ValueError("모임 상태를 확인해주세요.")
        host = await db.get(Member, host_id)
        if host is None or not host.active or not host.host_enabled:
            raise ValueError("Host 가능 사용자를 선택해주세요.")
        meeting = Meeting(
            place_name=place_name.strip(),
            place_url=validate_place_url(place_url),
            neighborhood=neighborhood.strip(),
            representative_menu=representative_menu.strip(),
            host_message=host_message.strip(),
            description_content="",
            start_at=start,
            capacity=capacity,
            status=meeting_status,
        )
        db.add(meeting)
        await db.flush()
        db.add(MeetingHost(meeting_id=meeting.meeting_id, member_id=host_id))
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        target = await get_hosted_meeting(db, member.member_id, meeting_id)
        return templates.TemplateResponse(
            request=request,
            name="admin/meeting_form.html",
            context=await meeting_form_context(request, db, admin, error=str(exc)),
            status_code=422,
        )
    return RedirectResponse("/admin/meetings", status_code=303)


@router.get("/admin/meetings/{meeting_id}/edit", response_class=HTMLResponse)
async def admin_meeting_edit_page(
    meeting_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    admin = await require_admin(request, db)
    target = await db.get(Meeting, meeting_id)
    if target is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="admin/meeting_form.html",
        context=await meeting_form_context(request, db, admin, target),
    )


@router.post("/admin/meetings/{meeting_id}/edit", response_class=HTMLResponse)
async def admin_meeting_edit(
    meeting_id: int,
    request: Request,
    place_name: str = Form(...),
    place_url: str = Form(""),
    neighborhood: str = Form(...),
    representative_menu: str = Form(...),
    host_message: str = Form(...),
    start_at: str = Form(...),
    capacity: int = Form(...),
    meeting_status: str = Form(...),
    host_id: int = Form(...),
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    verify_csrf(request, csrf)
    admin = await require_admin(request, db)
    target = await db.get(Meeting, meeting_id)
    if target is None:
        raise HTTPException(status_code=404)
    try:
        start = parse_meeting_time(start_at)
        if capacity < 1:
            raise ValueError("정원을 확인해주세요.")
        if meeting_status not in {"DRAFT", "OPEN", "CLOSED", "CANCELLED"}:
            raise ValueError("모임 상태를 확인해주세요.")
        host = await db.get(Member, host_id)
        if host is None or not host.active or not host.host_enabled:
            raise ValueError("Host 가능 사용자를 선택해주세요.")
        target.place_name = place_name.strip()
        target.place_url = validate_place_url(place_url)
        target.neighborhood = neighborhood.strip()
        target.representative_menu = representative_menu.strip()
        target.host_message = host_message.strip()
        target.description_content = ""
        target.start_at = start
        target.capacity = capacity
        target.status = meeting_status
        meeting_host = await db.get(MeetingHost, meeting_id)
        if meeting_host is None:
            db.add(MeetingHost(meeting_id=meeting_id, member_id=host_id))
        else:
            meeting_host.member_id = host_id
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="admin/meeting_form.html",
            context=await meeting_form_context(request, db, admin, target, str(exc)),
            status_code=422,
        )
    return RedirectResponse("/admin/meetings", status_code=303)


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


async def get_hosted_meeting(
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
        "csrf_token": csrf_token(request),
        "error": error,
        "seoul": ZoneInfo("Asia/Seoul"),
    }


@router.get("/host/meetings/{meeting_id}/edit", response_class=HTMLResponse)
async def host_meeting_edit_page(
    meeting_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    member = await current_member(request, db)
    target = await get_hosted_meeting(db, member.member_id, meeting_id)
    return templates.TemplateResponse(
        request=request,
        name="host/meeting_form.html",
        context=await host_meeting_form_context(request, db, member, target),
    )


@router.post("/host/meetings/{meeting_id}/edit", response_class=HTMLResponse)
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
    target = await get_hosted_meeting(db, member.member_id, meeting_id)
    try:
        start = parse_meeting_time(start_at)
        applied_count = await db.scalar(
            select(func.count())
            .select_from(Registration)
            .where(Registration.meeting_id == meeting_id)
        )
        if not all(
            value.strip()
            for value in (
                place_name,
                neighborhood,
                representative_menu,
                host_message,
            )
        ):
            raise ValueError("모임 정보를 모두 입력해주세요.")
        if capacity < 1:
            raise ValueError("정원을 확인해주세요.")
        if capacity < (applied_count or 0):
            raise ValueError("정원은 현재 신청 인원보다 작게 설정할 수 없습니다.")
        target.place_name = place_name.strip()
        target.place_url = validate_place_url(place_url)
        target.neighborhood = neighborhood.strip()
        target.representative_menu = representative_menu.strip()
        target.host_message = host_message.strip()
        target.start_at = start
        target.capacity = capacity
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="host/meeting_form.html",
            context=await host_meeting_form_context(
                request, db, member, target, str(exc)
            ),
            status_code=422,
        )
    request.session["flash"] = ("success", "모임 정보를 수정했습니다.")
    return RedirectResponse("/host", status_code=303)


@router.get("/host/meetings/{meeting_id}/registrations", response_class=HTMLResponse)
async def host_meeting_registrations(
    meeting_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    member = await current_member(request, db)
    meeting = await get_hosted_meeting(db, member.member_id, meeting_id)
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
