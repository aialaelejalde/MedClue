"""Test application startup, connected routes, and resource cleanup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import main
from medclue_api.config import Settings
from medclue_api.schemas import CimaPresentation, ImageAnalysisResult, OfficialUsesResult


@pytest.fixture
def backend(monkeypatch):
    settings = Settings(
        openai_api_key="test-key",
        openai_model="test-model",
        retry_token_secret="test-retry-secret-with-at-least-32-characters",
    )
    medication = CimaPresentation(
        name="EXAMPLE 500 mg COMPRIMIDOS",
        strength="500 mg",
        form="comprimido",
        registration_number="000001",
        national_code="000010",
    )
    cima = SimpleNamespace(
        get_presentation=AsyncMock(return_value=medication),
        get_official_indications=AsyncMock(return_value="Official indications"),
        close=AsyncMock(),
    )
    openai = SimpleNamespace(
        analyze_image=AsyncMock(return_value=ImageAnalysisResult(candidates=[])),
        translate_official_uses=AsyncMock(
            return_value=OfficialUsesResult(official_uses=["Supported use"])
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(main, "load_settings", Mock(return_value=settings))
    monkeypatch.setattr(main, "CimaClient", Mock(return_value=cima))
    monkeypatch.setattr(main, "OpenAIClient", Mock(return_value=openai))
    return SimpleNamespace(settings=settings, medication=medication, cima=cima, openai=openai)


def test_startup_initializes_clients_and_connects_both_routes(backend):
    with TestClient(main.app) as client:
        photo_result = client.post("/identify", files={"photo": ("package.jpg", b"photo", "image/jpeg")})
        verified_result = client.post("/verify", json={"national_code": "000010"})

        assert photo_result.status_code == 200
        assert photo_result.json()["status"] == "not_identified"
        assert verified_result.status_code == 200
        assert verified_result.json()["medication"] == backend.medication.model_dump()
        assert verified_result.json()["official_uses"] == ["Supported use"]
        main.load_settings.assert_called_once_with()
        main.CimaClient.assert_called_once_with()
        main.OpenAIClient.assert_called_once_with(backend.settings)
        backend.openai.analyze_image.assert_awaited_once_with(b"photo", "image/jpeg")
        backend.cima.get_presentation.assert_awaited_once_with("000010")


def test_shutdown_closes_clients_and_clears_service(backend):
    with TestClient(main.app):
        backend.cima.close.assert_not_awaited()
        backend.openai.close.assert_not_awaited()

    backend.cima.close.assert_awaited_once_with()
    backend.openai.close.assert_awaited_once_with()
    assert main.app.state.identification_service is None


@pytest.mark.parametrize("component", ["OpenAIClient", "IdentificationService"])
def test_startup_failure_closes_created_clients(backend, monkeypatch, component):
    monkeypatch.setattr(main, component, Mock(side_effect=RuntimeError("Startup failed")))

    with pytest.raises(RuntimeError, match="Startup failed"):
        with TestClient(main.app):
            pass

    backend.cima.close.assert_awaited_once_with()
    if component == "IdentificationService":
        backend.openai.close.assert_awaited_once_with()
    else:
        backend.openai.close.assert_not_awaited()


def test_one_close_failure_does_not_prevent_closing_the_other_client(backend):
    backend.openai.close.side_effect = RuntimeError("Close failed")

    with pytest.raises(RuntimeError, match="Close failed"):
        with TestClient(main.app):
            pass

    backend.openai.close.assert_awaited_once_with()
    backend.cima.close.assert_awaited_once_with()
    assert main.app.state.identification_service is None
