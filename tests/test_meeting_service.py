from datetime import datetime

import pytest

from app.models import Meeting
from app.services.meeting_service import (
    MeetingValidationError,
    parse_meeting_details,
    update_meeting_details,
)


def valid_details(capacity: int = 4):
    return parse_meeting_details(
        place_name="광교 라운지",
        place_url="https://map.naver.com/example",
        neighborhood="광교",
        representative_menu="파스타",
        host_message="편하게 만나요",
        start_at="2026-09-05T19:00",
        capacity=capacity,
    )


def test_meeting_details_normalize_shared_admin_and_host_input() -> None:
    details = valid_details()
    assert details.place_name == "광교 라운지"
    assert details.start_at.tzinfo is not None
    assert details.capacity == 4


def test_meeting_details_reject_invalid_url() -> None:
    with pytest.raises(MeetingValidationError):
        parse_meeting_details(
            place_name="장소",
            place_url="javascript:alert(1)",
            neighborhood="광교",
            representative_menu="메뉴",
            host_message="한마디",
            start_at="2026-09-05T19:00",
            capacity=4,
        )


def test_meeting_details_reject_non_ten_minute_start() -> None:
    with pytest.raises(MeetingValidationError, match="10분 단위"):
        parse_meeting_details(
            place_name="장소",
            place_url="",
            neighborhood="광교",
            representative_menu="메뉴",
            host_message="한마디",
            start_at="2026-09-05T19:05",
            capacity=4,
        )


@pytest.mark.asyncio
async def test_update_rejects_capacity_below_current_applicants() -> None:
    class FakeSession:
        async def scalar(self, statement):
            return 3

    meeting = Meeting(
        meeting_id=1,
        place_name="기존 장소",
        neighborhood="광교",
        representative_menu="기존 메뉴",
        host_message="기존 한마디",
        description_content="",
        start_at=datetime.fromisoformat("2026-09-05T19:00+09:00"),
        capacity=4,
        status="OPEN",
    )
    with pytest.raises(MeetingValidationError):
        await update_meeting_details(FakeSession(), meeting, valid_details(capacity=2))
