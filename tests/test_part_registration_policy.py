from app.services.part_registration_policy import part_registration_allowed


def test_first_member_from_part_is_allowed() -> None:
    assert part_registration_allowed(
        candidate_part_id=1,
        applicant_part_ids=[2, 2],
        active_part_member_count=2,
        distribution_meeting_count=5,
    )


def test_same_part_is_limited_to_one_when_meetings_are_sufficient() -> None:
    assert not part_registration_allowed(
        candidate_part_id=1,
        applicant_part_ids=[1, 2],
        active_part_member_count=5,
        distribution_meeting_count=5,
    )


def test_second_same_part_member_is_allowed_for_overflow_part() -> None:
    assert part_registration_allowed(
        candidate_part_id=1,
        applicant_part_ids=[1, 2],
        active_part_member_count=6,
        distribution_meeting_count=5,
    )


def test_only_one_part_can_have_two_members_in_a_meeting() -> None:
    assert not part_registration_allowed(
        candidate_part_id=1,
        applicant_part_ids=[1, 2, 2],
        active_part_member_count=6,
        distribution_meeting_count=5,
    )


def test_third_member_from_same_part_is_never_allowed() -> None:
    assert not part_registration_allowed(
        candidate_part_id=1,
        applicant_part_ids=[1, 1],
        active_part_member_count=10,
        distribution_meeting_count=5,
    )
