import pytest

from app.config import Settings


def test_non_local_environment_rejects_sqlite_database() -> None:
    with pytest.raises(ValueError, match="SQLite is only allowed"):
        Settings(app_env="production", database_url="sqlite:///./workflow_dev.db")


@pytest.mark.parametrize(
    "auth_secret_key",
    [
        "local-dev-auth-secret-change-me",
        " local-dev-auth-secret-change-me ",
        "change-this-in-production",
        "",
        "   ",
    ],
)
def test_non_local_environment_rejects_weak_auth_secret_key(auth_secret_key: str) -> None:
    with pytest.raises(ValueError, match="Default AUTH_SECRET_KEY"):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://workflow:password@postgres:5432/workflow",
            auth_secret_key=auth_secret_key,
        )


def test_production_environment_accepts_postgresql_database_url() -> None:
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg://workflow:password@postgres:5432/workflow",
        auth_secret_key="production-secret",
    )

    assert settings.database_url.startswith("postgresql+psycopg://")
