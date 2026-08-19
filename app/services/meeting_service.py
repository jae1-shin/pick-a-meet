from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Meeting, Registration


class MeetingValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MeetingDetails:
    place_name: str
    place_url: str | None
    neighborhood: str
    representative_menu: str
    host_message: str
    start_at: datetime
    capacity: int


def parse_meeting_details(
    *,
    place_name: str,
    place_url: str,
    neighborhood: str,
    representative_menu: str,
    host_message: str,
    start_at: str,
    capacity: int,
) -> MeetingDetails:
    text_values = {
        "place_name": place_name.strip(),
        "neighborhood": neighborhood.strip(),
        "representative_menu": representative_menu.strip(),
        "host_message": host_message.strip(),
    }
    if not all(text_values.values()):
        raise MeetingValidationError("모임 정보를 모두 입력해주세요.")
    if capacity < 1:
        raise MeetingValidationError("정원을 확인해주세요.")

    try:
        parsed_start = datetime.fromisoformat(start_at)
    except ValueError as exc:
        raise MeetingValidationError("시작 일시를 확인해주세요.") from exc
    if parsed_start.minute % 10 != 0 or parsed_start.second != 0:
        raise MeetingValidationError("시작 시간은 10분 단위로 선택해주세요.")
    if parsed_start.tzinfo is None:
        parsed_start = parsed_start.replace(tzinfo=ZoneInfo("Asia/Seoul"))

    cleaned_url = place_url.strip()
    if cleaned_url and not cleaned_url.startswith(("https://", "http://")):
        raise MeetingValidationError(
            "장소 링크는 http:// 또는 https://로 시작해야 합니다."
        )

    return MeetingDetails(
        place_name=text_values["place_name"],
        place_url=cleaned_url or None,
        neighborhood=text_values["neighborhood"],
        representative_menu=text_values["representative_menu"],
        host_message=text_values["host_message"],
        start_at=parsed_start,
        capacity=capacity,
    )


async def meeting_registration_count(db: AsyncSession, meeting_id: int) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(Registration)
        .where(Registration.meeting_id == meeting_id)
    ) or 0


def validate_meeting_status_change(status: str, applied_count: int) -> None:
    if status == "CANCELLED" and applied_count > 0:
        raise MeetingValidationError(
            "신청자가 있는 모임은 취소 상태로 변경할 수 없습니다."
        )


async def update_meeting_details(
    db: AsyncSession,
    meeting: Meeting,
    details: MeetingDetails,
    applied_count: int | None = None,
) -> None:
    if applied_count is None:
        applied_count = await meeting_registration_count(db, meeting.meeting_id)
    if details.capacity < applied_count:
        raise MeetingValidationError(
            "정원은 현재 신청 인원보다 작게 설정할 수 없습니다."
        )
    meeting.place_name = details.place_name
    meeting.place_url = details.place_url
    meeting.neighborhood = details.neighborhood
    meeting.representative_menu = details.representative_menu
    meeting.host_message = details.host_message
    meeting.description_content = ""
    meeting.start_at = details.start_at
    meeting.capacity = details.capacity
