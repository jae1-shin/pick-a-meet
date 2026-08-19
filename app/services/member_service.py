from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MeetingHost, Registration


class MemberValidationError(ValueError):
    pass


async def validate_member_permissions(
    db: AsyncSession,
    *,
    member_id: int | None,
    apply_enabled: bool,
    host_enabled: bool,
    active: bool,
) -> None:
    if host_enabled and apply_enabled:
        raise MemberValidationError("Host 사용자는 신청 권한을 N으로 설정해주세요.")
    if member_id is None:
        return

    registration_count = 0
    if not apply_enabled or not active:
        registration_count = await db.scalar(
            select(func.count())
            .select_from(Registration)
            .where(Registration.member_id == member_id)
        ) or 0

    if not active:
        hosted_count = await db.scalar(
            select(func.count())
            .select_from(MeetingHost)
            .where(MeetingHost.member_id == member_id)
        ) or 0
        if registration_count or hosted_count:
            raise MemberValidationError(
                "신청한 모임과 Host로 배정된 모임이 없어야 비활성화할 수 있습니다."
            )
    elif not apply_enabled and registration_count:
        raise MemberValidationError(
            "신청한 모임이 있는 사용자는 신청 권한을 N으로 변경할 수 없습니다."
        )
