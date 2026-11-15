"""Test the identification API endpoints."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from medclue_api.routes import MAX_PHOTO_BYTES, router
from medclue_api.schemas import CimaPresentation, IdentificationResponse, VerifyRequest


@pytest.fixture
def api():
    medication = CimaPresentation(
        name="EXAMPLE 500 mg COMPRIMIDOS",
        strength="500 mg",
        form="comprimido",
        registration_number="000001",
        national_code="000010",
    )
    result = IdentificationResponse(
        status="verified", medication=medication, official_uses=["Supported use"]
    )
    service = SimpleNamespace(
        identify=AsyncMock(return_value=result),
        process_selection_or_retry=AsyncMock(return_value=result),
    )
    app = FastAPI()
    app.state.identification_service = service
    app.include_router(router)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, service=service, app=app, result=result)


def test_identify_sends_original_photo_to_service_and_returns_json(api):
    response = api.client.post("/identify", files={"photo": ("package.png", b"original photo", "image/png")})

    assert response.status_code == 200
    assert response.json() == api.result.model_dump(mode="json")
    api.service.identify.assert_awaited_once_with(b"original photo", "image/png")
    api.service.process_selection_or_retry.assert_not_awaited()


@pytest.mark.parametrize(
    "photo, media_type, status_code",
    [(b"", "image/jpeg", 400), (b"photo", "image/gif", 415)],
)
def test_invalid_photo_is_rejected_before_identification(api, photo, media_type, status_code):
    response = api.client.post("/identify", files={"photo": ("package", photo, media_type)})

    assert response.status_code == status_code
    api.service.identify.assert_not_awaited()


@pytest.mark.parametrize("extra_bytes", [0, 1])
def test_photo_size_limit(api, extra_bytes):
    photo = b"x" * (MAX_PHOTO_BYTES + extra_bytes)

    response = api.client.post("/identify", files={"photo": ("package.jpg", photo, "image/jpeg")})

    if extra_bytes:
        assert response.status_code == 413
        assert response.json() == {"detail": "The photo is too large."}
        api.service.identify.assert_not_awaited()
    else:
        assert response.status_code == 200
        api.service.identify.assert_awaited_once_with(photo, "image/jpeg")


def test_identify_requires_a_photo(api):
    response = api.client.post("/identify")

    assert response.status_code == 422
    api.service.identify.assert_not_awaited()


@pytest.mark.parametrize(
    "selection",
    [
        {"candidate": {"name": "Example", "strength": "500 mg", "form": "tablet"}},
        {"national_code": "000010"},
        {"retry_token": "signed-retry-token"},
    ],
)
def test_verify_accepts_each_selection_without_image_analysis(api, selection):
    response = api.client.post("/verify", json=selection)

    assert response.status_code == 200
    assert response.json() == api.result.model_dump(mode="json")
    api.service.process_selection_or_retry.assert_awaited_once_with(VerifyRequest.model_validate(selection))
    api.service.identify.assert_not_awaited()


@pytest.mark.parametrize(
    "selection", [{}, {"national_code": "000010", "retry_token": "token"}],
)
def test_verify_rejects_missing_or_conflicting_selections(api, selection):
    response = api.client.post("/verify", json=selection)

    assert response.status_code == 422
    api.service.process_selection_or_retry.assert_not_awaited()


@pytest.mark.parametrize(
    "error, status_code",
    [
        (ValueError("The retry token is invalid."), 400),
        (ValueError("The retry token has expired."), 400),
        (LookupError("The selected CIMA presentation was not found."), 404),
    ],
)
def test_verify_converts_selection_errors_to_http_errors(api, error, status_code):
    api.service.process_selection_or_retry.side_effect = error

    response = api.client.post("/verify", json={"retry_token": "token"})

    assert response.status_code == status_code
    assert response.json() == {"detail": str(error)}


@pytest.mark.parametrize("status", ["not_identified", "connection_error", "timeout"])
def test_identification_states_remain_process_results(api, status):
    result = IdentificationResponse(
        status=status,
        failed_step="image_analysis" if status != "not_identified" else None,
    )
    api.service.identify.return_value = result

    response = api.client.post("/identify", files={"photo": ("package.jpg", b"photo", "image/jpeg")})

    assert response.status_code == 200
    assert response.json() == result.model_dump(mode="json")


@pytest.mark.parametrize("service_state", ["missing", None])
def test_service_must_be_initialized(api, service_state):
    if service_state == "missing":
        del api.app.state.identification_service
    else:
        api.app.state.identification_service = None

    response = api.client.post("/verify", json={"national_code": "000010"})

    assert response.status_code == 503
    api.service.process_selection_or_retry.assert_not_awaited()


@pytest.mark.parametrize("endpoint", ["/identify", "/verify"])
def test_disconnect_cancels_active_processing(api, monkeypatch, endpoint):
    started = []
    cancelled = []

    async def blocked(*args):
        started.append(True)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    async def is_disconnected(request):
        return bool(started)

    api.service.identify.side_effect = blocked
    api.service.process_selection_or_retry.side_effect = blocked
    monkeypatch.setattr(Request, "is_disconnected", is_disconnected)

    if endpoint == "/identify":
        response = api.client.post(endpoint, files={"photo": ("package.jpg", b"photo", "image/jpeg")})
    else:
        response = api.client.post(endpoint, json={"national_code": "000010"})

    assert response.status_code == 499
    assert cancelled == [True]
