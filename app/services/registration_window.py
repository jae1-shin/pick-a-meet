from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RegistrationSchedule


_opens_at: datetime | None = None
_show_host_information = False


class RegistrationWindowValidationError(ValueError):
    pass


def set_registration_opens_at(value: datetime | None) -> None:
    global _opens_at
    if value is not None and value.tzinfo is None:
        raise ValueError("Registration opening time must include a timezone")
    _opens_at = value.astimezone(timezone.utc) if value else None


def registration_opens_at() -> datetime | None:
    return _opens_at


def set_show_host_information(value: bool) -> None:
    global _show_host_information
    _show_host_information = value


def show_host_information() -> bool:
    return _show_host_information


def registration_is_open(now: datetime | None = None) -> bool:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Current time must include a timezone")
    return _opens_at is None or current.astimezone(timezone.utc) >= _opens_at


def registration_remaining_ms(now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Current time must include a timezone")
    if _opens_at is None:
        return 0
    return max(
        int((_opens_at - current.astimezone(timezone.utc)).total_seconds() * 1000),
        0,
    )


async def load_registration_window(db: AsyncSession) -> None:
    schedule = await db.get(RegistrationSchedule, 1)
    set_registration_opens_at(schedule.opens_at if schedule else None)
    set_show_host_information(
        schedule.show_host_information if schedule else False
    )


def parse_registration_opening(
    *, mode: str, open_date: str, open_hour: int, open_minute: int
) -> datetime | None:
    if mode == "immediate":
        return None
    try:
        if mode != "scheduled":
            raise ValueError
        if not 0 <= open_hour <= 23 or open_minute not in range(0, 60, 10):
            raise ValueError
        return datetime.fromisoformat(
            f"{open_date}T{open_hour:02d}:{open_minute:02d}"
        ).replace(tzinfo=ZoneInfo("Asia/Seoul"))
    except ValueError as exc:
        raise RegistrationWindowValidationError(
            "신청 시작 일시를 확인해주세요."
        ) from exc


async def update_registration_window(
    db: AsyncSession,
    opens_at: datetime | None,
) -> None:
    schedule = await db.get(RegistrationSchedule, 1)
    if schedule is None:
        schedule = RegistrationSchedule(
            schedule_id=1,
            opens_at=opens_at,
            show_host_information=False,
        )
        db.add(schedule)
    else:
        schedule.opens_at = opens_at
    await db.commit()
    set_registration_opens_at(opens_at)


async def update_host_information_visibility(
    db: AsyncSession, host_information_visible: bool
) -> None:
    schedule = await db.get(RegistrationSchedule, 1)
    if schedule is None:
        schedule = RegistrationSchedule(
            schedule_id=1,
            opens_at=None,
            show_host_information=host_information_visible,
        )
        db.add(schedule)
    else:
        schedule.show_host_information = host_information_visible
    await db.commit()
    set_show_host_information(host_information_visible)
