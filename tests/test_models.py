from app.models import Base


def test_registration_has_one_active_meeting_per_member_constraint() -> None:
    registration = Base.metadata.tables["registration"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in registration.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("member_id",) in unique_columns


def test_all_required_tables_are_registered() -> None:
    assert {
        "part",
        "module",
        "member",
        "login_history",
        "meeting",
        "meeting_host",
        "registration",
        "registration_history",
        "registration_schedule",
    }.issubset(Base.metadata.tables)


def test_host_and_apply_permissions_cannot_both_be_enabled() -> None:
    member = Base.metadata.tables["member"]
    check_sql = {
        str(constraint.sqltext)
        for constraint in member.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    assert "NOT (host_enabled AND apply_enabled)" in check_sql
