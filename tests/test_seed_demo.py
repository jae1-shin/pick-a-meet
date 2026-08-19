from collections import Counter, defaultdict

from scripts.seed_demo import (
    DEMO_MEETINGS,
    DEMO_USERS,
    SAMPLE_ASSIGNMENTS,
)


def test_demo_users_match_realistic_role_and_part_shape() -> None:
    assert len(DEMO_USERS) == 120
    assert len({user["login_id"] for user in DEMO_USERS}) == 120
    assert len({user["employee_no"] for user in DEMO_USERS}) == 120
    assert all(
        int(user["login_id"][-2:]) == int(user["employee_no"])
        if user["login_id"].startswith("leader")
        else int(user["login_id"].removeprefix("member"))
        == int(user["employee_no"])
        for user in DEMO_USERS
    )

    leaders = [user for user in DEMO_USERS if user["host_enabled"]]
    admins = [user for user in DEMO_USERS if user["admin_enabled"]]
    assert len(leaders) == 18
    assert len(admins) == 3
    assert sum(user["host_enabled"] and user["admin_enabled"] for user in DEMO_USERS) == 1
    assert sum(not user["host_enabled"] and user["admin_enabled"] for user in DEMO_USERS) == 2

    active_part_counts = Counter(
        user["part"] for user in DEMO_USERS if user["active"]
    )
    assert sorted(active_part_counts.values(), reverse=True) == [32, 30, 28, 15, 15]


def test_demo_meetings_and_registrations_exercise_part_rule() -> None:
    assert len(DEMO_MEETINGS) == 18
    assert sum(
        meeting["status"] in ("OPEN", "CLOSED") for meeting in DEMO_MEETINGS
    ) == 18
    assert len({meeting["host_login_id"] for meeting in DEMO_MEETINGS}) == 18

    users = {user["login_id"]: user for user in DEMO_USERS}
    assert len({login_id for login_id, _ in SAMPLE_ASSIGNMENTS}) == len(
        SAMPLE_ASSIGNMENTS
    )

    parts_by_meeting: dict[str, list[str]] = defaultdict(list)
    for login_id, place_name in SAMPLE_ASSIGNMENTS:
        parts_by_meeting[place_name].append(users[login_id]["part"])
    for parts in parts_by_meeting.values():
        counts = Counter(parts)
        assert max(counts.values()) <= 2
        assert sum(count == 2 for count in counts.values()) <= 1

    assert any(
        2 in Counter(parts).values() for parts in parts_by_meeting.values()
    )
