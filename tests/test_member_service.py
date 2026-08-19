import pytest

from app.services.member_service import (
    MemberValidationError,
    validate_member_permissions,
)


@pytest.mark.asyncio
async def test_host_must_not_have_apply_permission() -> None:
    with pytest.raises(MemberValidationError, match="신청 권한을 N"):
        await validate_member_permissions(
            object(),
            member_id=None,
            apply_enabled=True,
            host_enabled=True,
            active=True,
        )


@pytest.mark.asyncio
async def test_apply_permission_cannot_be_removed_with_registration() -> None:
    class FakeSession:
        async def scalar(self, statement):
            return 1

    with pytest.raises(MemberValidationError, match="신청한 모임"):
        await validate_member_permissions(
            FakeSession(),
            member_id=7,
            apply_enabled=False,
            host_enabled=False,
            active=True,
        )


@pytest.mark.asyncio
async def test_inactive_requires_no_registration_or_hosted_meeting() -> None:
    class FakeSession:
        def __init__(self):
            self.results = iter((0, 1))

        async def scalar(self, statement):
            return next(self.results)

    with pytest.raises(MemberValidationError, match="Host로 배정"):
        await validate_member_permissions(
            FakeSession(),
            member_id=7,
            apply_enabled=False,
            host_enabled=False,
            active=False,
        )
