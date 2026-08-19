from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routers.auth import post_login_destination
from app.services.registration_service import apply_to_meeting, cancel_registration
from app.services.registration_window import (
    RegistrationWindowValidationError,
    parse_registration_opening,
    registration_is_open,
    set_registration_opens_at,
)


def test_registration_window_uses_memory_time_and_privileged_bypass() -> None:
    now = datetime.now(timezone.utc)
    try:
        set_registration_opens_at(now + timedelta(hours=1))
        assert not registration_is_open(now)
        assert post_login_destination(
            SimpleNamespace(admin_enabled=False, host_enabled=False)
        ) == "/waiting"
        assert post_login_destination(
            SimpleNamespace(admin_enabled=True, host_enabled=False)
        ) == "/meetings"
        assert post_login_destination(
            SimpleNamespace(admin_enabled=False, host_enabled=True)
        ) == "/meetings"

        set_registration_opens_at(now - timedelta(seconds=1))
        assert registration_is_open(now)
    finally:
        set_registration_opens_at(None)


def test_registration_opening_requires_ten_minute_interval() -> None:
    with pytest.raises(RegistrationWindowValidationError):
        parse_registration_opening(
            mode="scheduled",
            open_date="2026-09-01",
            open_hour=19,
            open_minute=5,
        )


@pytest.mark.asyncio
async def test_registration_changes_stop_before_database_transaction() -> None:
    class NoDatabaseSession:
        def begin(self):
            raise AssertionError("database transaction must not start")

    try:
        set_registration_opens_at(datetime.now(timezone.utc) + timedelta(hours=1))
        assert await apply_to_meeting(NoDatabaseSession(), 1, 1) == (
            "REGISTRATION_NOT_STARTED"
        )
        assert await cancel_registration(NoDatabaseSession(), 1) == (
            "REGISTRATION_NOT_STARTED"
        )
    finally:
        set_registration_opens_at(None)
