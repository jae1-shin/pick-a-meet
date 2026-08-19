from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import LoginHistory, Member
from app.services.session_service import client_ip, csrf_token, verify_csrf
from app.services.registration_window import registration_is_open


router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def post_login_destination(member: Member) -> str:
    privileged = member.admin_enabled or member.host_enabled
    return "/meetings" if privileged or registration_is_open() else "/waiting"


def login_context(
    request: Request,
    error: str | None = None,
    login_id: str = "",
    employee_no: str = "",
) -> dict[str, object]:
    return {
        "request": request,
        "csrf_token": csrf_token(request),
        "error": error,
        "login_id": login_id,
        "employee_no": employee_no,
    }


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if request.session.get("member_id"):
        return RedirectResponse("/meetings", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context=login_context(request))


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    login_id: str = Form(...),
    employee_no: str = Form(...),
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    verify_csrf(request, csrf)
    ip = client_ip(request)
    member = await db.scalar(
        select(Member).where(
            Member.login_id == login_id.strip(),
            Member.employee_no == employee_no.strip(),
        )
    )
    if member is None:
        db.add(LoginHistory(login_ip=ip, ip_changed=False, login_result="FAILED"))
        await db.commit()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context=login_context(
                request,
                "ID 또는 사번을 확인해주세요.",
                login_id,
                employee_no,
            ),
            status_code=401,
        )
    if not member.active:
        db.add(
            LoginHistory(
                member_id=member.member_id,
                login_ip=ip,
                ip_changed=False,
                login_result="INACTIVE",
            )
        )
        await db.commit()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context=login_context(
                request,
                "사용이 중지된 계정입니다. 관리자에게 문의해주세요.",
                login_id,
                employee_no,
            ),
            status_code=403,
        )

    if member.last_login_ip and member.last_login_ip != ip:
        request.session.clear()
        request.session["pending_member_id"] = member.member_id
        request.session["pending_ip"] = ip
        return templates.TemplateResponse(
            request=request,
            name="confirm_ip.html",
            context={
                "request": request,
                "csrf_token": csrf_token(request),
                "last_login_at": member.last_login_at,
            },
        )

    now = datetime.now(timezone.utc)
    member.last_login_ip = ip
    member.last_login_at = now
    db.add(
        LoginHistory(
            member_id=member.member_id,
            login_ip=ip,
            ip_changed=False,
            login_result="SUCCESS",
        )
    )
    await db.commit()
    request.session.clear()
    request.session["member_id"] = member.member_id
    request.session["session_kind"] = "login"
    csrf_token(request)
    return RedirectResponse(post_login_destination(member), status_code=303)


@router.post("/login/confirm-ip")
async def confirm_ip(
    request: Request,
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    verify_csrf(request, csrf)
    member_id = request.session.get("pending_member_id")
    ip = request.session.get("pending_ip")
    member = await db.get(Member, member_id) if member_id else None
    if member is None or not ip or not member.active:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    member.last_login_ip = ip
    member.last_login_at = datetime.now(timezone.utc)
    db.add(
        LoginHistory(
            member_id=member.member_id,
            login_ip=ip,
            ip_changed=True,
            login_result="SUCCESS_AFTER_IP_CONFIRM",
        )
    )
    await db.commit()
    request.session.clear()
    request.session["member_id"] = member.member_id
    request.session["session_kind"] = "login"
    csrf_token(request)
    return RedirectResponse(post_login_destination(member), status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf: str = Form(...)) -> RedirectResponse:
    verify_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.post("/impersonation/return")
async def return_from_impersonation(
    request: Request,
    csrf: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    verify_csrf(request, csrf)
    if request.session.get("session_kind") != "impersonation":
        return RedirectResponse("/meetings", status_code=303)
    admin_id = request.session.get("impersonator_member_id")
    admin = await db.get(Member, admin_id) if admin_id else None
    if admin is None or not admin.active or not admin.admin_enabled:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    token = csrf_token(request)
    request.session.clear()
    request.session["member_id"] = admin.member_id
    request.session["session_kind"] = "login"
    request.session["admin_console_verified"] = True
    request.session["csrf_token"] = token
    return RedirectResponse("/admin", status_code=303)
