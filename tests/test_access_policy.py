from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.policies import access


@pytest.mark.parametrize(
    ("admin_enabled", "allowed"),
    [(False, False), (True, True)],
)
@pytest.mark.asyncio
async def test_admin_role_policy_uses_independent_admin_flag(
    monkeypatch: pytest.MonkeyPatch,
    admin_enabled: bool,
    allowed: bool,
) -> None:
    member = SimpleNamespace(admin_enabled=admin_enabled, host_enabled=True)

    async def fake_current_member(request, db):
        return member

    monkeypatch.setattr(access, "current_member", fake_current_member)
    if allowed:
        assert await access.require_admin_role(object(), object()) is member
    else:
        with pytest.raises(HTTPException) as exc_info:
            await access.require_admin_role(object(), object())
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_console_policy_requires_second_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member = SimpleNamespace(admin_enabled=True, host_enabled=True)

    async def fake_admin_role(request, db):
        return member

    monkeypatch.setattr(access, "require_admin_role", fake_admin_role)
    request = SimpleNamespace(session={})
    with pytest.raises(HTTPException) as exc_info:
        await access.require_admin_console(request, object())
    assert exc_info.value.status_code == 403

    request.session["admin_console_verified"] = True
    assert await access.require_admin_console(request, object()) is member


@pytest.mark.asyncio
async def test_hosted_meeting_policy_rejects_unassigned_meeting() -> None:
    class FakeSession:
        async def scalar(self, statement):
            return None

    with pytest.raises(HTTPException) as exc_info:
        await access.require_hosted_meeting(FakeSession(), 10, 20)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_hosted_meeting_policy_returns_assigned_meeting() -> None:
    meeting = object()

    class FakeSession:
        async def scalar(self, statement):
            return meeting

    assert await access.require_hosted_meeting(FakeSession(), 10, 20) is meeting
