from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.meeting_view import build_meeting_filter_context


def test_meeting_filters_are_reusable_for_waiting_page() -> None:
    views = [
        {
            "meeting": SimpleNamespace(neighborhood="광교"),
            "start_at": datetime(2026, 9, 5, 19, tzinfo=ZoneInfo("Asia/Seoul")),
        },
        {
            "meeting": SimpleNamespace(neighborhood="강남"),
            "start_at": datetime(2026, 9, 6, 18, tzinfo=ZoneInfo("Asia/Seoul")),
        },
    ]

    context = build_meeting_filter_context(
        views,
        neighborhood_filters=["광교"],
        date_filters=None,
        base_path="/waiting",
    )

    assert len(context["meeting_views"]) == 1
    assert context["meeting_views"][0]["meeting"].neighborhood == "광교"
    assert all(
        option["href"].startswith("/waiting")
        for option in context["neighborhood_options"]
    )
