from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Meeting, MeetingHost, Member, Module, Registration
from app.services.part_registration_policy import part_registration_allowed
from app.services.registration_policy import (
    applicant_registration_denial_reason,
    meeting_registration_denial_reason,
)
from app.services.registration_window import show_host_information


KOREAN_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def korean_time(value) -> str:
    period = "오전" if value.hour < 12 else "오후"
    hour = value.hour % 12 or 12
    return f"{period} {hour}:{value.strftime('%M')}"


async def load_applicants(
    db: AsyncSession, meeting_ids: list[int]
) -> dict[int, list[Member]]:
    applicants: dict[int, list[Member]] = {meeting_id: [] for meeting_id in meeting_ids}
    if not meeting_ids:
        return applicants
    rows = (
        await db.execute(
            select(Registration.meeting_id, Member)
            .join(Member, Member.member_id == Registration.member_id)
            .options(joinedload(Member.module).joinedload(Module.part))
            .where(Registration.meeting_id.in_(meeting_ids))
            .order_by(Registration.meeting_id, Registration.registered_at)
        )
    ).all()
    for meeting_id, applicant in rows:
        applicants[meeting_id].append(applicant)
    return applicants


async def load_meeting_hosts(
    db: AsyncSession, meeting_ids: list[int]
) -> dict[int, Member]:
    if not meeting_ids:
        return {}
    rows = (
        await db.execute(
            select(MeetingHost.meeting_id, Member)
            .join(Member, Member.member_id == MeetingHost.member_id)
            .options(joinedload(Member.module).joinedload(Module.part))
            .where(MeetingHost.meeting_id.in_(meeting_ids))
        )
    ).all()
    return {meeting_id: host for meeting_id, host in rows}


async def load_public_meeting_views(
    db: AsyncSession,
    member: Member,
    *,
    registration_open: bool,
) -> tuple[list[dict[str, object]], bool]:
    count_subquery = (
        select(Registration.meeting_id, func.count().label("applied_count"))
        .group_by(Registration.meeting_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Meeting, func.coalesce(count_subquery.c.applied_count, 0))
            .outerjoin(
                count_subquery,
                count_subquery.c.meeting_id == Meeting.meeting_id,
            )
            .where(Meeting.status.in_(("OPEN", "CLOSED", "CANCELLED")))
            .order_by(Meeting.start_at)
        )
    ).all()
    active_registration = await db.scalar(
        select(Registration).where(Registration.member_id == member.member_id)
    )
    is_open_host = bool(
        await db.scalar(
            select(func.count())
            .select_from(MeetingHost)
            .join(Meeting, Meeting.meeting_id == MeetingHost.meeting_id)
            .where(
                MeetingHost.member_id == member.member_id,
                Meeting.status == "OPEN",
            )
        )
    )
    applicants = await load_applicants(
        db, [meeting.meeting_id for meeting, _ in rows]
    )
    host_information_visible = show_host_information()
    hosts = (
        await load_meeting_hosts(
            db, [meeting.meeting_id for meeting, _ in rows]
        )
        if host_information_visible
        else {}
    )
    current_part_id = member.module.part_id
    active_part_member_count = await db.scalar(
        select(func.count())
        .select_from(Member)
        .join(Module, Module.module_id == Member.module_id)
        .where(
            Module.part_id == current_part_id,
            Member.active.is_(True),
        )
    )
    distribution_meeting_count = sum(
        1 for meeting, _ in rows if meeting.status in ("OPEN", "CLOSED")
    )
    seoul = ZoneInfo("Asia/Seoul")
    views = []
    for meeting, applied_count in rows:
        start_at = meeting.start_at.astimezone(seoul)
        part_allowed = part_registration_allowed(
            candidate_part_id=current_part_id,
            applicant_part_ids=(
                applicant.module.part_id
                for applicant in applicants[meeting.meeting_id]
            ),
            active_part_member_count=active_part_member_count or 0,
            distribution_meeting_count=distribution_meeting_count,
        )
        applicant_denial_reason = applicant_registration_denial_reason(
            registration_open=registration_open,
            member_active=member.active,
            apply_enabled=member.apply_enabled,
            is_open_host=is_open_host,
            has_active_registration=active_registration is not None,
        )
        meeting_denial_reason = meeting_registration_denial_reason(
            meeting_exists=True,
            meeting_status=meeting.status,
            applied_count=applied_count,
            capacity=meeting.capacity,
            part_allowed=part_allowed,
        )
        views.append(
            {
                "meeting": meeting,
                "applied_count": applied_count,
                "remaining_count": max(meeting.capacity - applied_count, 0),
                "start_at": start_at,
                "weekday": KOREAN_WEEKDAYS[start_at.weekday()],
                "is_registered": bool(
                    active_registration
                    and active_registration.meeting_id == meeting.meeting_id
                ),
                "has_active_registration": active_registration is not None,
                "can_apply": (
                    applicant_denial_reason is None
                    and meeting_denial_reason is None
                ),
                "part_limit_reached": not part_allowed,
                "applicants": applicants[meeting.meeting_id],
                "host": hosts.get(meeting.meeting_id),
                "show_host_information": host_information_visible,
            }
        )
    return views, is_open_host


def build_meeting_filter_context(
    meeting_views: list[dict[str, object]],
    *,
    neighborhood_filters: list[str] | None,
    date_filters: list[str] | None,
    base_path: str,
    base_params: list[tuple[str, str]] | None = None,
) -> dict[str, object]:
    fixed_params = base_params or []
    neighborhood_options = [
        {"value": value, "label": value}
        for value in sorted(
            {item["meeting"].neighborhood for item in meeting_views}
        )
    ]
    date_options = [
        {
            "value": value,
            "label": f"{start.strftime('%m.%d')} ({KOREAN_WEEKDAYS[start.weekday()]})",
        }
        for value, start in sorted(
            {
                item["start_at"].date().isoformat(): item["start_at"]
                for item in meeting_views
            }.items()
        )
    ]
    selected_neighborhoods = {
        value
        for value in (neighborhood_filters or [])
        if len(value) <= 100
        and value in {option["value"] for option in neighborhood_options}
    }
    selected_dates = {
        value
        for value in (date_filters or [])
        if len(value) <= 100
        and value in {option["value"] for option in date_options}
    }
    neighborhoods_in_order = [
        option["value"]
        for option in neighborhood_options
        if option["value"] in selected_neighborhoods
    ]
    dates_in_order = [
        option["value"]
        for option in date_options
        if option["value"] in selected_dates
    ]

    def url(params: list[tuple[str, str]]) -> str:
        query = urlencode(fixed_params + params)
        return f"{base_path}?{query}" if query else base_path

    for option in neighborhood_options:
        value = option["value"]
        toggled = [item for item in neighborhoods_in_order if item != value]
        if value not in selected_neighborhoods:
            toggled.append(value)
        option["selected"] = value in selected_neighborhoods
        option["href"] = url(
            [("neighborhood", item) for item in toggled]
            + [("date", item) for item in dates_in_order]
        )
    for option in date_options:
        value = option["value"]
        toggled = [item for item in dates_in_order if item != value]
        if value not in selected_dates:
            toggled.append(value)
        option["selected"] = value in selected_dates
        option["href"] = url(
            [("neighborhood", item) for item in neighborhoods_in_order]
            + [("date", item) for item in toggled]
        )

    filtered_views = meeting_views
    if selected_neighborhoods:
        filtered_views = [
            item
            for item in filtered_views
            if item["meeting"].neighborhood in selected_neighborhoods
        ]
    if selected_dates:
        filtered_views = [
            item
            for item in filtered_views
            if item["start_at"].date().isoformat() in selected_dates
        ]
    return {
        "meeting_views": filtered_views,
        "selected_neighborhoods": neighborhoods_in_order,
        "selected_dates": dates_in_order,
        "neighborhood_options": neighborhood_options,
        "date_options": date_options,
        "neighborhood_clear_href": url(
            [("date", item) for item in dates_in_order]
        ),
        "date_clear_href": url(
            [("neighborhood", item) for item in neighborhoods_in_order]
        ),
        "preserved_filter_params": [
            ("neighborhood", item) for item in neighborhoods_in_order
        ]
        + [("date", item) for item in dates_in_order],
    }
