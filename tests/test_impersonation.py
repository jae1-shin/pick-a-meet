from types import SimpleNamespace

import pytest

from app.routers import admin as admin_router
from app.routers import auth as auth_router


class FakeSession:
    def __init__(self, member):
        self.member = member

    async def get(self, model, member_id):
        return self.member if self.member.member_id == member_id else None


@pytest.mark.asyncio
async def test_admin_switch_creates_an_explicit_impersonation_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_admin = SimpleNamespace(member_id=1)
    target = SimpleNamespace(
        member_id=2,
        active=True,
        admin_enabled=False,
        host_enabled=False,
    )

    async def fake_require_admin_console(request, db):
        return original_admin

    monkeypatch.setattr(
        admin_router, "require_admin_console", fake_require_admin_console
    )
    request = SimpleNamespace(
        session={
            "member_id": 1,
            "session_kind": "login",
            "admin_console_verified": True,
            "csrf_token": "token",
        }
    )

    response = await admin_router.admin_impersonate_member(
        member_id=2,
        request=request,
        csrf="token",
        db=FakeSession(target),
    )

    assert response.status_code == 303
    assert request.session == {
        "member_id": 2,
        "session_kind": "impersonation",
        "impersonator_member_id": 1,
        "csrf_token": "token",
    }


@pytest.mark.asyncio
async def test_return_restores_only_an_active_admin_session() -> None:
    original_admin = SimpleNamespace(
        member_id=1,
        active=True,
        admin_enabled=True,
    )
    request = SimpleNamespace(
        session={
            "member_id": 2,
            "session_kind": "impersonation",
            "impersonator_member_id": 1,
            "csrf_token": "token",
        }
    )

    response = await auth_router.return_from_impersonation(
        request=request,
        csrf="token",
        db=FakeSession(original_admin),
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert request.session == {
        "member_id": 1,
        "session_kind": "login",
        "admin_console_verified": True,
        "csrf_token": "token",
    }
