import hmac
from datetime import datetime
from pathlib import Path
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


@router.get("/meetings", response_class=HTMLResponse)
async def meetings_page(
    request: Request,
    group_by: str = Query("neighborhood", pattern="^(neighborhood|date)$"),
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
    meeting_views = [
        {
            "meeting": meeting,
            "applied_count": applied_count,
            "remaining_count": max(meeting.capacity - applied_count, 0),
            "start_at": meeting.start_at.astimezone(seoul),
            "end_at": meeting.end_at.astimezone(seoul),
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
        }
        for meeting, applied_count in rows
    ]
    if group_by == "date":
        meeting_views.sort(
            key=lambda item: (
                item["start_at"].date(),
                item["meeting"].neighborhood,
                item["start_at"],
            )
        )
        group_key = lambda item: item["start_at"].date().isoformat()
        group_title = lambda item: item["start_at"].strftime("%Y년 %m월 %d일")
    else:
        meeting_views.sort(
            key=lambda item: (item["meeting"].neighborhood, item["start_at"])
        )
        group_key = lambda item: item["meeting"].neighborhood
        group_title = lambda item: item["meeting"].neighborhood

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
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    member = await current_member(request, db)
    if not member.admin_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if not request.session.get("admin_console_verified"):
        return RedirectResponse("/admin/unlock", status_code=303)
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
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    admin = await require_admin(request, db)
    rows = (
        await db.execute(
            select(Meeting, Member)
            .join(MeetingHost, MeetingHost.meeting_id == Meeting.meeting_id)
            .join(Member, Member.member_id == MeetingHost.member_id)
            .order_by(Meeting.start_at)
        )
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="admin/meetings.html",
        context={"member": admin, "rows": rows, "seoul": ZoneInfo("Asia/Seoul")},
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
    description_content: str = Form(""),
    start_at: str = Form(...),
    end_at: str = Form(...),
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
        end = parse_meeting_time(end_at)
        if end <= start or capacity < 1:
            raise ValueError("종료 일시와 정원을 확인해주세요.")
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
            description_content=description_content.strip(),
            start_at=start,
            end_at=end,
            capacity=capacity,
            status=meeting_status,
        )
        db.add(meeting)
        await db.flush()
        db.add(MeetingHost(meeting_id=meeting.meeting_id, member_id=host_id))
        await db.commit()
    except ValueError as exc:
        await db.rollback()
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
    description_content: str = Form(""),
    start_at: str = Form(...),
    end_at: str = Form(...),
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
        end = parse_meeting_time(end_at)
        if end <= start or capacity < 1:
            raise ValueError("종료 일시와 정원을 확인해주세요.")
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
        target.description_content = description_content.strip()
        target.start_at = start
        target.end_at = end
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
    return templates.TemplateResponse(
        request=request,
        name="host/index.html",
        context={"member": member, "meetings": hosted, "csrf_token": csrf_token(request)},
    )


@router.get("/host/meetings/{meeting_id}/registrations", response_class=HTMLResponse)
async def host_meeting_registrations(
    meeting_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    member = await current_member(request, db)
    meeting = await db.scalar(
        select(Meeting)
        .join(MeetingHost, MeetingHost.meeting_id == Meeting.meeting_id)
        .where(
            Meeting.meeting_id == meeting_id,
            MeetingHost.member_id == member.member_id,
        )
    )
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
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
        },
    )
