"""Test backend configuration loaded from environment variables."""

import pytest

from medclue_api import config


@pytest.fixture(autouse=True)
def configured_environment(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("RETRY_TOKEN_SECRET", "test-retry-secret-with-at-least-32-characters")


def test_settings_strip_outer_spaces_from_environment_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "  test-key  ")
    monkeypatch.setenv("OPENAI_MODEL", "  test-model  ")
    monkeypatch.setenv("RETRY_TOKEN_SECRET", "  test-retry-secret-with-at-least-32-characters  ")

    settings = config.load_settings()

    assert settings == config.Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        retry_token_secret="test-retry-secret-with-at-least-32-characters",
    )


def test_missing_model_uses_the_default(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL")

    settings = config.load_settings()

    assert settings.openai_model == "gpt-6.1-terra"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_api_key_is_rejected(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("OPENAI_API_KEY")
    else:
        monkeypatch.setenv("OPENAI_API_KEY", value)

    with pytest.raises(ValueError, match="OPENAI_API_KEY must be set and cannot be blank"):
        config.load_settings()


@pytest.mark.parametrize("value", ["", "   "])
def test_explicitly_blank_model_is_rejected(monkeypatch, value):
    monkeypatch.setenv("OPENAI_MODEL", value)

    with pytest.raises(ValueError, match="OPENAI_MODEL cannot be blank"):
        config.load_settings()


@pytest.mark.parametrize("value", [None, "", " " * 32, "s" * 31, " " + "s" * 31 + " "])
def test_missing_or_short_retry_secret_is_rejected(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("RETRY_TOKEN_SECRET")
    else:
        monkeypatch.setenv("RETRY_TOKEN_SECRET", value)

    with pytest.raises(ValueError, match="RETRY_TOKEN_SECRET must contain at least 32 characters"):
        config.load_settings()


def test_retry_secret_with_exactly_32_characters_is_accepted(monkeypatch):
    secret = "s" * 32
    monkeypatch.setenv("RETRY_TOKEN_SECRET", secret)

    settings = config.load_settings()

    assert settings.retry_token_secret == secret
