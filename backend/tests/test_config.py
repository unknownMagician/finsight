import pytest

from app.core.config import Settings


def test_cors_origins_accepts_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINSIGHT_CORS_ORIGINS", "http://a.test, http://b.test")
    assert Settings(_env_file=None).cors_origins == ["http://a.test", "http://b.test"]


def test_secrets_are_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINSIGHT_ANTHROPIC_API_KEY", "sk-ant-very-secret")
    monkeypatch.setenv("FINSIGHT_DATABASE_URL", "postgresql+psycopg://u:hunter2@db/x")
    settings = Settings(_env_file=None)
    assert "very-secret" not in repr(settings)
    assert "hunter2" not in repr(settings)


def test_invalid_environment_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINSIGHT_ENVIRONMENT", "staging-typo")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
