from app.config import Settings


def test_database_url_is_built_from_environment_fields() -> None:
    settings = Settings(
        database_host="db.internal",
        database_port=5433,
        database_name="meetings",
        database_user="service",
        database_password="secret",
    )

    assert settings.database_url == (
        "postgresql+asyncpg://service:secret@db.internal:5433/meetings"
    )
