def applicant_registration_denial_reason(
    *,
    registration_open: bool,
    member_active: bool,
    apply_enabled: bool,
    is_open_host: bool,
    has_active_registration: bool,
) -> str | None:
    """Return the first applicant-level reason that prevents registration."""
    if not registration_open:
        return "REGISTRATION_NOT_STARTED"
    if not member_active or not apply_enabled:
        return "NOT_ELIGIBLE"
    if is_open_host:
        return "HOST_NOT_ALLOWED"
    if has_active_registration:
        return "ALREADY_REGISTERED"
    return None


def meeting_registration_denial_reason(
    *,
    meeting_exists: bool,
    meeting_status: str | None,
    applied_count: int,
    capacity: int,
    part_allowed: bool,
) -> str | None:
    """Return the first meeting-level reason that prevents registration."""
    if not meeting_exists or meeting_status != "OPEN":
        return "MEETING_NOT_OPEN"
    if applied_count >= capacity:
        return "MEETING_FULL"
    if not part_allowed:
        return "PART_LIMIT_REACHED"
    return None
