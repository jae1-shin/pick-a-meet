from app.services.registration_policy import (
    applicant_registration_denial_reason,
    meeting_registration_denial_reason,
)


def test_applicant_policy_returns_reasons_in_transaction_order() -> None:
    assert applicant_registration_denial_reason(
        registration_open=False,
        member_active=True,
        apply_enabled=True,
        is_open_host=False,
        has_active_registration=False,
    ) == "REGISTRATION_NOT_STARTED"
    assert applicant_registration_denial_reason(
        registration_open=True,
        member_active=True,
        apply_enabled=True,
        is_open_host=True,
        has_active_registration=True,
    ) == "HOST_NOT_ALLOWED"


def test_registration_policies_allow_only_a_fully_eligible_registration() -> None:
    assert applicant_registration_denial_reason(
        registration_open=True,
        member_active=True,
        apply_enabled=True,
        is_open_host=False,
        has_active_registration=False,
    ) is None
    assert meeting_registration_denial_reason(
        meeting_exists=True,
        meeting_status="OPEN",
        applied_count=5,
        capacity=6,
        part_allowed=True,
    ) is None


def test_meeting_policy_distinguishes_full_and_part_limit() -> None:
    assert meeting_registration_denial_reason(
        meeting_exists=True,
        meeting_status="OPEN",
        applied_count=6,
        capacity=6,
        part_allowed=False,
    ) == "MEETING_FULL"
    assert meeting_registration_denial_reason(
        meeting_exists=True,
        meeting_status="OPEN",
        applied_count=5,
        capacity=6,
        part_allowed=False,
    ) == "PART_LIMIT_REACHED"
