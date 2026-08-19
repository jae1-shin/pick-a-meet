import hmac
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
from app.policies.access import require_admin_console, require_admin_role
from app.services.meeting_service import (
    MeetingValidationError,
    parse_meeting_details,
    update_meeting_details,
)
from app.services.meeting_view import KOREAN_WEEKDAYS, korean_time, load_applicants
from app.services.session_service import csrf_token, verify_csrf


router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
templates.env.filters["korean_time"] = korean_time
settings = get_settings()


async def get_or_create_module(
    db: AsyncSession, part_name: str, module_name: str
) -> Module:
    clean_part = part_name.strip()
    clean_module = module_name.strip()
    part = await db.scalar(select(Part).where(Part.name == clean_part))
    if part is None:
        part = Part(name=clean_part)
        db.add(part)
        await db.flush()
    module = await db.scalar(
        select(Module).where(
            Module.part_id == part.part_id,
            Module.name == clean_module,
        )
    )
    if module is None:
        module = Module(part_id=part.part_id, name=clean_module)
        db.add(module)
        await db.flush()
    return module


@router.get("", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    sort: str = Query("name", max_length=30),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    member = await require_admin_role(request, db)
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
    direction = (
        sort_columns[sort].desc() if order == "desc" else sort_columns[sort].asc()
    )
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
            "flash": request.session.pop("flash", None),
        },
    )


@router.get("/unlock", response_class=HTMLResponse)
async def admin_unlock_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    member = await require_admin_role(request, db)
    if request.session.get("admin_console_verified"):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="admin/unlock.html",
        context={"member": member, "csrf_token": csrf_token(request), "error": None},
    )


@router.post("/unlock", response_class=HTMLResponse)
async def admin_unlock(
    request: Request,
    password: str = Form(...),
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    verify_csrf(request, csrf)
    member = await require_admin_role(request, db)
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


@router.get("/members/new", response_class=HTMLResponse)
async def admin_member_new_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    admin = await require_admin_console(request, db)
    return templates.TemplateResponse(
        request=request,
        name="admin/member_form.html",
        context=member_form_context(request, admin),
    )


@router.post("/members/new", response_class=HTMLResponse)
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
    admin = await require_admin_console(request, db)
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
    request.session["flash"] = ("success", "사용자를 등록했습니다.")
    return RedirectResponse("/admin", status_code=303)


async def load_member(db: AsyncSession, member_id: int) -> Member:
    target = await db.scalar(
        select(Member)
        .options(joinedload(Member.module).joinedload(Module.part))
        .where(Member.member_id == member_id)
    )
    if target is None:
        raise HTTPException(status_code=404)
    return target


@router.get("/members/{member_id}/edit", response_class=HTMLResponse)
async def admin_member_edit_page(
    member_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    admin = await require_admin_console(request, db)
    target = await load_member(db, member_id)
    return templates.TemplateResponse(
        request=request,
        name="admin/member_form.html",
        context=member_form_context(request, admin, target),
    )


@router.post("/members/{member_id}/edit", response_class=HTMLResponse)
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
    admin = await require_admin_console(request, db)
    target = await load_member(db, member_id)
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
        target = await load_member(db, member_id)
        return templates.TemplateResponse(
            request=request,
            name="admin/member_form.html",
            context=member_form_context(
                request, admin, target, "이미 사용 중인 ID 또는 사번입니다."
            ),
            status_code=409,
        )
    request.session["flash"] = ("success", "사용자 정보를 수정했습니다.")
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
    applied_count = 0
    if target is not None:
        host_id = await db.scalar(
            select(MeetingHost.member_id).where(
                MeetingHost.meeting_id == target.meeting_id
            )
        )
        applied_count = await db.scalar(
            select(func.count())
            .select_from(Registration)
            .where(Registration.meeting_id == target.meeting_id)
        ) or 0
    return {
        "request": request,
        "member": admin,
        "target": target,
        "hosts": hosts,
        "host_id": host_id,
        "applied_count": applied_count,
        "is_admin_form": True,
        "form_title": "모임 수정" if target else "모임 생성",
        "back_url": "/admin/meetings",
        "back_label": "모임 관리로",
        "csrf_token": csrf_token(request),
        "error": error,
        "seoul": ZoneInfo("Asia/Seoul"),
    }


@router.get("/meetings", response_class=HTMLResponse)
async def admin_meetings_page(
    request: Request,
    sort: str = Query("start_at", max_length=30),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    admin = await require_admin_console(request, db)
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
    direction = (
        sort_columns[sort].desc() if order == "desc" else sort_columns[sort].asc()
    )
    rows = (
        await db.execute(
            select(Meeting, Member, applied_count)
            .join(MeetingHost, MeetingHost.meeting_id == Meeting.meeting_id)
            .join(Member, Member.member_id == MeetingHost.member_id)
            .outerjoin(
                count_subquery,
                count_subquery.c.meeting_id == Meeting.meeting_id,
            )
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
            "flash": request.session.pop("flash", None),
        },
    )


@router.get("/meetings/new", response_class=HTMLResponse)
async def admin_meeting_new_page(
    request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    admin = await require_admin_console(request, db)
    return templates.TemplateResponse(
        request=request,
        name="meetings/meeting_form.html",
        context=await meeting_form_context(request, db, admin),
    )


def validate_admin_meeting_fields(meeting_status: str, host: Member | None) -> None:
    if meeting_status not in {"DRAFT", "OPEN", "CLOSED", "CANCELLED"}:
        raise MeetingValidationError("모임 상태를 확인해주세요.")
    if host is None or not host.active or not host.host_enabled:
        raise MeetingValidationError("Host 가능 사용자를 선택해주세요.")


@router.post("/meetings/new", response_class=HTMLResponse)
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
    admin = await require_admin_console(request, db)
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
        host = await db.get(Member, host_id)
        validate_admin_meeting_fields(meeting_status, host)
        meeting = Meeting(
            place_name=details.place_name,
            place_url=details.place_url,
            neighborhood=details.neighborhood,
            representative_menu=details.representative_menu,
            host_message=details.host_message,
            description_content="",
            start_at=details.start_at,
            capacity=details.capacity,
            status=meeting_status,
        )
        db.add(meeting)
        await db.flush()
        db.add(MeetingHost(meeting_id=meeting.meeting_id, member_id=host_id))
        await db.commit()
    except MeetingValidationError as exc:
        await db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="meetings/meeting_form.html",
            context=await meeting_form_context(request, db, admin, error=str(exc)),
            status_code=422,
        )
    request.session["flash"] = ("success", "모임을 생성했습니다.")
    return RedirectResponse("/admin/meetings", status_code=303)


@router.get("/meetings/{meeting_id}/edit", response_class=HTMLResponse)
async def admin_meeting_edit_page(
    meeting_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    admin = await require_admin_console(request, db)
    target = await db.get(Meeting, meeting_id)
    if target is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="meetings/meeting_form.html",
        context=await meeting_form_context(request, db, admin, target),
    )


@router.post("/meetings/{meeting_id}/edit", response_class=HTMLResponse)
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
    admin = await require_admin_console(request, db)
    target = await db.get(Meeting, meeting_id)
    if target is None:
        raise HTTPException(status_code=404)
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
        host = await db.get(Member, host_id)
        validate_admin_meeting_fields(meeting_status, host)
        await update_meeting_details(db, target, details)
        target.status = meeting_status
        meeting_host = await db.get(MeetingHost, meeting_id)
        if meeting_host is None:
            db.add(MeetingHost(meeting_id=meeting_id, member_id=host_id))
        else:
            meeting_host.member_id = host_id
        await db.commit()
    except MeetingValidationError as exc:
        await db.rollback()
        target = await db.get(Meeting, meeting_id)
        if target is None:
            raise HTTPException(status_code=404) from exc
        return templates.TemplateResponse(
            request=request,
            name="meetings/meeting_form.html",
            context=await meeting_form_context(request, db, admin, target, str(exc)),
            status_code=422,
        )
    request.session["flash"] = ("success", "모임 정보를 수정했습니다.")
    return RedirectResponse("/admin/meetings", status_code=303)
