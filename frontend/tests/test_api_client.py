"""Test backend communication."""

import asyncio
import json

import httpx
import pytest

from medclue_mobile.api_client import (MAX_PHOTO_BYTES, ApiConnectionError, ApiError, ApiTimeoutError, MedClueApiClient, PhotoTooLargeError)


@pytest.fixture
def api_client(monkeypatch):
    requests = []
    responses = []

    async def handle_request(request):
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return await response(request)
        return response

    real_client = httpx.AsyncClient

    def create_client(**kwargs):
        return real_client(**kwargs, transport=httpx.MockTransport(handle_request), trust_env=False)

    monkeypatch.setattr("medclue_mobile.api_client.httpx.AsyncClient", create_client)
    client = MedClueApiClient("https://medclue.test")
    yield client, requests, responses
    asyncio.run(client.close())


@pytest.mark.parametrize("media_type", ["image/jpeg", "image/png", "image/webp"])
def test_identify_sends_the_original_photo_as_multipart(api_client, media_type):
    client, requests, responses = api_client
    responses.append(httpx.Response(200, json={"status": "not_identified"}))

    result = asyncio.run(client.identify(b"original photo", media_type))

    assert result == {"status": "not_identified"}
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://medclue.test/identify"
    assert requests[0].headers["content-type"].startswith("multipart/form-data;")
    assert b'name="photo"' in requests[0].content
    assert f"Content-Type: {media_type}".encode("ascii") in requests[0].content
    assert b"original photo" in requests[0].content


@pytest.mark.parametrize("extra_bytes", [0, 1])
def test_photo_size_limit_is_checked_before_sending(api_client, extra_bytes):
    client, requests, responses = api_client
    photo = b"x" * (MAX_PHOTO_BYTES + extra_bytes)

    if extra_bytes:
        with pytest.raises(PhotoTooLargeError, match="The photo is too large"):
            asyncio.run(client.identify(photo))
        assert requests == []
    else:
        responses.append(httpx.Response(200, json={"status": "not_identified"}))
        assert asyncio.run(client.identify(photo)) == {"status": "not_identified"}
        assert len(requests) == 1


@pytest.mark.parametrize(
    "selection",
    [
        {"candidate": {"name": "Example", "strength": None, "form": None}},
        {"candidate": {"name": "Example", "strength": None, "form": None, "national_code": "998625.4"}},
        {"candidate": {"name": "Example", "strength": None, "form": None, "national_code": None}},
        {"national_code": "000010"},
        {"retry_token": "signed-token"},
    ],
)
def test_verify_sends_only_the_selected_data(api_client, selection):
    client, requests, responses = api_client
    responses.append(httpx.Response(200, json={"status": "not_identified"}))

    asyncio.run(client.send_selection_or_retry(**selection))

    assert requests[0].method == "POST"
    assert str(requests[0].url) == "https://medclue.test/verify"
    assert json.loads(requests[0].content) == selection


def test_identify_returns_timeout_response(api_client):
    client, _, responses = api_client
    result = {
        "status": "timeout",
        "failed_step": "cima_verification",
        "suggested_candidate": {"name": "Example", "strength": None, "form": None},
        "retry_token": "signed-token",
    }
    responses.append(httpx.Response(200, json=result))

    assert asyncio.run(client.identify(b"photo")) == result


@pytest.mark.parametrize(
    "status_code, detail",
    [(413, "The photo is too large."), (400, "The retry token has expired.")],
)
def test_http_errors_keep_the_backend_message_and_status(api_client, status_code, detail):
    client, requests, responses = api_client
    responses.append(httpx.Response(status_code, json={"detail": detail}))

    expected_error = PhotoTooLargeError if status_code == 413 else ApiError
    with pytest.raises(expected_error, match=detail) as error:
        if status_code == 413:
            asyncio.run(client.identify(b"photo"))
        else:
            asyncio.run(client.send_selection_or_retry(retry_token="token"))

    assert error.value.status_code == status_code
    assert len(requests) == 1
    assert requests[0].url.path == ("/identify" if status_code == 413 else "/verify")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, json={"status": "unknown"}),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
    ],
)
def test_invalid_backend_response_is_rejected(api_client, response):
    client, _, responses = api_client
    responses.append(response)

    with pytest.raises(ApiError, match="invalid response"):
        asyncio.run(client.identify(b"photo"))


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("Failure"), httpx.ReadTimeout("Timeout")],
)
def test_network_failures_raise_connection_error_without_automatic_retry(api_client, failure):
    client, requests, responses = api_client
    responses.append(failure)

    with pytest.raises(ApiConnectionError):
        asyncio.run(client.identify(b"photo"))

    assert len(requests) == 1


def test_global_request_deadline_stops_waiting(api_client, monkeypatch):
    client, requests, responses = api_client
    monkeypatch.setattr("medclue_mobile.api_client.IDENTIFICATION_TIMEOUT_SECONDS", 0.05)
    cancelled = []

    async def blocked(request):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    responses.append(blocked)
    with pytest.raises(ApiTimeoutError):
        asyncio.run(client.identify(b"photo"))

    assert cancelled == [True]
    assert len(requests) == 1


def test_cancellation_propagates_to_the_active_request(api_client):
    client, _, responses = api_client
    cancelled = []

    async def cancel_request():
        started = asyncio.Event()

        async def blocked(request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

        responses.append(blocked)
        task = asyncio.create_task(client.identify(b"photo"))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_request())
    assert cancelled == [True]


def test_personal_record_fields_cannot_be_sent_as_a_candidate(api_client):
    client, requests, _ = api_client
    candidate = {"name": "Example", "strength": None, "form": None, "notes": "Private note"}

    with pytest.raises(ValueError, match="optionally national_code"):
        asyncio.run(client.send_selection_or_retry(candidate=candidate))

    assert requests == []


@pytest.mark.parametrize("national_code", [998625, False])
def test_candidate_national_code_must_be_text_or_null(api_client, national_code):
    client, requests, _ = api_client
    candidate = {"name": "Example", "strength": None, "form": None, "national_code": national_code}

    with pytest.raises(ValueError, match="text or null"):
        asyncio.run(client.send_selection_or_retry(candidate=candidate))

    assert requests == []


def test_conflicting_selections_are_rejected_without_a_request(api_client):
    client, requests, _ = api_client

    with pytest.raises(ValueError, match="Send one"):
        asyncio.run(client.send_selection_or_retry(national_code="000010", retry_token="token"))

    assert requests == []


@pytest.mark.parametrize(
    "backend_url, message",
    [
        ("http://medclue.test", "HTTPS"),
        ("https://user:password@medclue.test", "credentials, a query, or a fragment"),
        ("https://medclue.test?key=value", "credentials, a query, or a fragment"),
        ("https://medclue.test#section", "credentials, a query, or a fragment"),
    ],
)
def test_invalid_backend_url_is_rejected(backend_url, message):
    with pytest.raises(ValueError, match=message):
        MedClueApiClient(backend_url)
