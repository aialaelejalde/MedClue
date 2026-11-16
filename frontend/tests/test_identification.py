"""Test identification sessions, user selections, retries, and late responses."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from medclue_mobile.api_client import (
    ApiConnectionError,
    ApiError,
    ApiTimeoutError,
    PhotoTooLargeError,
)
from medclue_mobile.identification import IdentificationSession


@pytest.fixture
def identification():
    candidate = {"name": "Example", "strength": "500 mg", "form": "tablet"}
    medication = {**candidate, "registration_number": "000001", "national_code": "000010"}
    verified = {"status": "verified", "medication": medication, "official_uses": ["Supported use"]}
    api = SimpleNamespace(
        identify=AsyncMock(return_value=verified),
        send_selection_or_retry=AsyncMock(return_value=verified),
    )
    return SimpleNamespace(
        session=IdentificationSession(api), api=api,
        candidate=candidate, medication=medication, verified=verified,
    )


@pytest.mark.parametrize("status", ["verified", "not_identified", "no_match", "multiple_matches"])
def test_completed_results_are_kept_without_automatic_requests(identification, status):
    context = identification
    result = {"status": status}
    context.api.identify.return_value = result

    assert asyncio.run(context.session.identify(b"original photo", "image/png")) == result
    assert context.session.result == result
    assert context.session.photo == b"original photo"
    assert context.session.media_type == "image/png"
    assert not context.session.is_running
    assert context.session.can_retry == (status == "not_identified")
    context.api.identify.assert_awaited_once_with(b"original photo", "image/png")
    context.api.send_selection_or_retry.assert_not_awaited()


@pytest.mark.parametrize("option_type", ["candidates", "presentations"])
def test_selected_match_is_verified_without_repeating_image_analysis(identification, option_type):
    context = identification
    option = context.candidate if option_type == "candidates" else context.medication
    context.api.identify.return_value = {"status": "multiple_matches", option_type: [option, {**option, "name": "Other"}]}

    async def select():
        await context.session.identify(b"photo")
        return await context.session.select_match(0)

    assert asyncio.run(select()) == context.verified
    expected = {"candidate": option} if option_type == "candidates" else {"national_code": "000010"}
    context.api.send_selection_or_retry.assert_awaited_once_with(**expected)
    assert context.api.identify.await_count == 1
    assert context.session.photo == b"photo"


@pytest.mark.parametrize("index", [-1, 2, True])
def test_invalid_selection_does_not_change_possible_matches(identification, index):
    context = identification
    result = {"status": "multiple_matches", "candidates": [context.candidate, context.candidate]}
    context.api.identify.return_value = result

    async def select():
        await context.session.identify(b"photo")
        with pytest.raises(ValueError, match="valid possible match"):
            await context.session.select_match(index)

    asyncio.run(select())
    assert context.session.result == result
    context.api.send_selection_or_retry.assert_not_awaited()


@pytest.mark.parametrize("step, status", [
    ("cima_verification", "connection_error"),
    ("official_uses_retrieval", "timeout"),
    ("uses_translation", "timeout"),
])
def test_backend_retry_uses_only_the_signed_token(identification, step, status):
    context = identification
    failure = {
        "status": status, "failed_step": step,
        "retry_token": "signed-token", "suggested_candidate": context.candidate,
    }
    context.api.identify.return_value = failure

    async def retry():
        assert await context.session.identify(b"photo") == failure
        assert context.session.can_retry
        return await context.session.retry()

    assert asyncio.run(retry()) == context.verified
    context.api.send_selection_or_retry.assert_awaited_once_with(retry_token="signed-token")
    assert context.api.identify.await_count == 1
    assert not context.session.can_retry


@pytest.mark.parametrize("step", ["official_uses_retrieval", "uses_translation"])
@pytest.mark.parametrize("network_failure", [False, True])
def test_verified_uses_retry_preserves_medication_and_skips_photo(identification, step, network_failure):
    context = identification
    partial = {
        "status": "verified", "medication": context.medication,
        "official_uses": [], "failed_step": step, "retry_token": "signed-token",
    }
    context.api.identify.return_value = partial
    context.api.send_selection_or_retry.side_effect = (
        [ApiConnectionError("Offline"), context.verified] if network_failure else [context.verified]
    )

    async def retry():
        assert await context.session.identify(b"photo") == partial
        assert context.session.can_retry
        if network_failure:
            assert await context.session.retry() == partial
            assert context.session.can_retry
        assert await context.session.retry() == context.verified
        assert not context.session.can_retry

    asyncio.run(retry())
    context.api.identify.assert_awaited_once_with(b"photo", "image/jpeg")
    assert all(call.kwargs == {"retry_token": "signed-token"} for call in context.api.send_selection_or_retry.await_args_list)


@pytest.mark.parametrize("error", [
    ApiConnectionError("Offline"), ApiTimeoutError("Too slow"),
    ApiError("Server error", status_code=500),
    ApiError("Unavailable", status_code=503),
])
def test_local_initial_failure_retries_with_original_photo(identification, error):
    context = identification
    context.api.identify.side_effect = [error, context.verified]

    async def retry():
        result = await context.session.identify(b"same photo", "image/webp")
        assert result["status"] == ("timeout" if isinstance(error, ApiTimeoutError) else "connection_error")
        assert result["suggested_candidate"] is None
        assert context.session.can_retry
        return await context.session.retry()

    assert asyncio.run(retry()) == context.verified
    assert context.api.identify.await_count == 2
    assert all(call.args == (b"same photo", "image/webp") for call in context.api.identify.await_args_list)
    context.api.send_selection_or_retry.assert_not_awaited()


def test_backend_image_failure_retries_same_photo(identification):
    context = identification
    context.api.identify.side_effect = [
        {"status": "timeout", "failed_step": "image_analysis"}, context.verified
    ]

    async def retry():
        await context.session.identify(b"photo")
        return await context.session.retry()

    assert asyncio.run(retry()) == context.verified
    assert context.api.identify.await_count == 2
    context.api.send_selection_or_retry.assert_not_awaited()


@pytest.mark.parametrize("option_type", ["candidates", "presentations"])
@pytest.mark.parametrize("error", [ApiTimeoutError("Too slow"), ApiError("Unavailable", status_code=503)])
def test_local_selection_failure_retains_name_and_retries_selection(identification, option_type, error):
    context = identification
    option = context.candidate if option_type == "candidates" else context.medication
    context.api.identify.return_value = {"status": "multiple_matches", option_type: [option, option]}
    context.api.send_selection_or_retry.side_effect = [error, context.verified]

    async def retry():
        await context.session.identify(b"photo")
        result = await context.session.select_match(0)
        assert result["suggested_candidate"] == context.candidate
        assert "official_uses" not in result
        return await context.session.retry()

    assert asyncio.run(retry()) == context.verified
    assert context.api.identify.await_count == 1
    assert context.api.send_selection_or_retry.await_args_list[0] == context.api.send_selection_or_retry.await_args_list[1]


@pytest.mark.parametrize("error", [ApiConnectionError("Offline"), ApiError("Bad gateway", status_code=502)])
def test_local_retry_failure_keeps_token_name_and_failed_step(identification, error):
    context = identification
    context.api.identify.return_value = {
        "status": "timeout", "failed_step": "uses_translation",
        "retry_token": "first-token", "suggested_candidate": context.candidate,
    }
    context.api.send_selection_or_retry.side_effect = [error, context.verified]

    async def retry():
        await context.session.identify(b"photo")
        result = await context.session.retry()
        assert result["retry_token"] == "first-token"
        assert result["failed_step"] == "uses_translation"
        assert result["suggested_candidate"] == context.candidate
        return await context.session.retry()

    assert asyncio.run(retry()) == context.verified
    assert all(call.kwargs == {"retry_token": "first-token"} for call in context.api.send_selection_or_retry.await_args_list)


@pytest.mark.parametrize("error", [PhotoTooLargeError("Too large"), ValueError("Invalid photo"), ApiError("Invalid response")])
def test_input_and_api_errors_are_not_converted_to_no_match(identification, error):
    context = identification
    context.api.identify.side_effect = error

    with pytest.raises(type(error), match=str(error)):
        asyncio.run(context.session.identify(b"photo"))

    assert context.session.photo == b"photo"
    assert context.session.result is None
    assert not context.session.is_running
    assert not context.session.can_retry


def test_expired_retry_token_is_reported_without_restarting_image_analysis(identification):
    context = identification
    context.api.identify.return_value = {
        "status": "timeout", "failed_step": "cima_verification", "retry_token": "expired-token"
    }
    context.api.send_selection_or_retry.side_effect = ApiError("The retry token has expired.", status_code=400)

    async def retry():
        await context.session.identify(b"photo")
        with pytest.raises(ApiError, match="expired"):
            await context.session.retry()

    asyncio.run(retry())
    assert context.session.photo == b"photo"
    assert not context.session.can_retry
    assert context.api.identify.await_count == 1


@pytest.mark.parametrize("after_selection", [False, True])
def test_missing_retry_token_does_not_repeat_completed_steps(identification, after_selection):
    context = identification
    failure = {"status": "timeout", "failed_step": "uses_translation"}
    context.api.identify.return_value = failure
    context.api.send_selection_or_retry.return_value = failure

    async def fail():
        if after_selection:
            context.api.identify.return_value = {
                "status": "multiple_matches", "candidates": [context.candidate, context.candidate]
            }
            await context.session.identify(b"photo")
        with pytest.raises(ApiError, match="data needed to retry"):
            if after_selection:
                await context.session.select_match(0)
            else:
                await context.session.identify(b"photo")

    asyncio.run(fail())
    assert context.session.result is None
    assert not context.session.can_retry
    assert context.session.photo == b"photo"
    assert context.api.identify.await_count == 1
    assert context.api.send_selection_or_retry.await_count == int(after_selection)


def test_cancel_discards_temporary_photo_and_result(identification):
    session = identification.session
    asyncio.run(session.identify(b"photo"))
    session.cancel()
    assert session.photo is None
    assert session.media_type is None
    assert session.result is None
    assert not session.can_retry
    assert not session.is_running


def test_late_result_after_cancellation_cannot_restore_the_session(identification):
    context = identification

    async def cancel():
        started = asyncio.Event()
        release = asyncio.Event()

        async def late_request(*args):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return context.verified

        context.api.identify.side_effect = late_request
        task = asyncio.create_task(context.session.identify(b"photo"))
        await asyncio.wait_for(started.wait(), timeout=1)
        context.session.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    assert context.session.photo is None
    assert context.session.result is None
    assert not context.session.is_running


def test_old_request_cannot_clear_the_loading_state_of_a_new_request(identification):
    context = identification

    async def overlap():
        old_started = asyncio.Event()
        new_started = asyncio.Event()
        release_new = asyncio.Event()

        async def request(photo, media_type):
            if photo == b"old photo":
                old_started.set()
                await asyncio.Event().wait()
            new_started.set()
            await release_new.wait()
            return context.verified

        context.api.identify.side_effect = request
        old = asyncio.create_task(context.session.identify(b"old photo"))
        await asyncio.wait_for(old_started.wait(), timeout=1)
        new = asyncio.create_task(context.session.identify(b"new photo"))
        await asyncio.wait_for(new_started.wait(), timeout=1)
        with pytest.raises(asyncio.CancelledError):
            await old
        assert context.session.is_running
        assert context.session.result is None
        release_new.set()
        assert await new == context.verified

    asyncio.run(overlap())
    assert context.session.photo == b"new photo"
    assert not context.session.is_running


@pytest.mark.parametrize("late_error", [None, ApiError("Old failure"), ApiError("Old server failure", status_code=503)])
def test_new_attempt_rejects_old_responses_and_errors(identification, late_error):
    context = identification

    async def overlap():
        started = asyncio.Event()
        release = asyncio.Event()

        async def old_request(*args):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            if late_error is not None:
                raise late_error
            return {"status": "not_identified"}

        context.api.identify.side_effect = old_request
        old = asyncio.create_task(context.session.identify(b"old photo"))
        await asyncio.wait_for(started.wait(), timeout=1)
        assert context.session.is_running
        context.api.identify.side_effect = None
        assert await context.session.identify(b"new photo") == context.verified
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await old

    asyncio.run(overlap())
    assert context.session.photo == b"new photo"
    assert context.session.result == context.verified
    assert not context.session.is_running


@pytest.mark.parametrize("cancel_caller", [False, True])
def test_cancellation_stops_request_and_clears_session(identification, cancel_caller):
    context = identification

    async def cancel():
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def blocked(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        context.api.identify.side_effect = blocked
        task = asyncio.create_task(context.session.identify(b"photo"))
        await asyncio.wait_for(started.wait(), timeout=1)
        assert context.session.is_running
        if cancel_caller:
            task.cancel()
        else:
            context.session.cancel()
            assert context.session.photo is None
            assert not context.session.is_running
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()

    asyncio.run(cancel())
    assert context.session.photo is None
    assert not context.session.is_running
    assert context.session.result is None
    assert not context.session.can_retry


@pytest.mark.parametrize("action", ["retry", "select_match"])
def test_retry_and_selection_are_rejected_while_identification_is_running(identification, action):
    context = identification

    async def reject_action():
        started = asyncio.Event()

        async def blocked(*args):
            started.set()
            await asyncio.Event().wait()

        context.api.identify.side_effect = blocked
        task = asyncio.create_task(context.session.identify(b"photo"))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            with pytest.raises(ValueError):
                if action == "retry":
                    await context.session.retry()
                else:
                    await context.session.select_match(0)
            assert context.session.is_running
            assert context.session.photo == b"photo"
            context.api.identify.assert_awaited_once_with(b"photo", "image/jpeg")
            context.api.send_selection_or_retry.assert_not_awaited()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(reject_action())


def test_results_cannot_be_changed_through_external_dictionaries(identification):
    context = identification
    expected = deepcopy(context.verified)
    result = asyncio.run(context.session.identify(b"photo"))
    result["medication"]["name"] = "Changed return value"
    snapshot = context.session.result
    snapshot["official_uses"].clear()
    context.verified["medication"]["name"] = "Changed backend value"
    assert context.session.result == expected


def test_fresh_attempt_discards_previous_token_and_suggested_name(identification):
    context = identification
    context.api.identify.side_effect = [
        {"status": "timeout", "failed_step": "uses_translation", "retry_token": "old-token",
         "suggested_candidate": context.candidate},
        ApiTimeoutError("Too slow"),
    ]

    async def restart():
        await context.session.identify(b"old photo")
        return await context.session.identify(b"new photo")

    result = asyncio.run(restart())
    assert result["suggested_candidate"] is None
    assert result["retry_token"] is None
    assert result["failed_step"] == "image_analysis"
    assert context.session.photo == b"new photo"
    context.api.send_selection_or_retry.assert_not_awaited()


def test_retry_and_selection_require_the_matching_session_state(identification):
    async def invalid_actions():
        assert identification.session.photo is None
        assert identification.session.media_type is None
        assert identification.session.result is None
        assert not identification.session.is_running
        assert not identification.session.can_retry
        with pytest.raises(ValueError):
            await identification.session.retry()
        with pytest.raises(ValueError):
            await identification.session.select_match(0)
        await identification.session.identify(b"photo")
        with pytest.raises(ValueError):
            await identification.session.retry()
        with pytest.raises(ValueError):
            await identification.session.select_match(0)

    asyncio.run(invalid_actions())


@pytest.mark.parametrize("option_type, status, include_null_candidate", [
    ("candidates", "timeout", False),
    ("candidates", "connection_error", True),
    ("presentations", "timeout", True),
    ("presentations", "connection_error", False),
])
@pytest.mark.parametrize("failure_on_retry", [False, True])
def test_backend_failure_keeps_selected_match_when_suggested_candidate_is_missing(
    identification, option_type, status, include_null_candidate, failure_on_retry
):
    context = identification
    option = context.candidate if option_type == "candidates" else context.medication
    context.api.identify.return_value = {"status": "multiple_matches", option_type: [option, option]}
    failure = {"status": status, "failed_step": "cima_verification", "retry_token": "first-token"}
    if include_null_candidate:
        failure["suggested_candidate"] = None
    original_failure = deepcopy(failure)
    context.api.send_selection_or_retry.side_effect = (
        [{**failure, "suggested_candidate": context.candidate}, failure]
        if failure_on_retry else [failure]
    )

    async def receive_failure():
        await context.session.identify(b"photo")
        result = await context.session.select_match(0)
        if failure_on_retry:
            result = await context.session.retry()
        return result

    result = asyncio.run(receive_failure())
    assert result["status"] == status
    assert result["suggested_candidate"] == context.candidate
    assert result.get("medication") is None
    assert not result.get("official_uses")
    assert context.session.can_retry
    assert failure == original_failure
    assert context.api.identify.await_count == 1


def test_retry_uses_the_latest_token_returned_by_the_backend(identification):
    context = identification
    context.api.identify.return_value = {
        "status": "timeout", "failed_step": "cima_verification", "retry_token": "first-token"
    }
    context.api.send_selection_or_retry.side_effect = [
        {"status": "timeout", "failed_step": "uses_translation", "retry_token": "second-token"},
        context.verified,
    ]

    async def retry_twice():
        await context.session.identify(b"photo")
        await context.session.retry()
        return await context.session.retry()

    assert asyncio.run(retry_twice()) == context.verified
    assert context.api.identify.await_count == 1
    assert [call.kwargs for call in context.api.send_selection_or_retry.await_args_list] == [
        {"retry_token": "first-token"},
        {"retry_token": "second-token"},
    ]


def test_backend_suggested_candidate_takes_precedence_over_selected_match(identification):
    context = identification
    context.api.identify.return_value = {"status": "multiple_matches", "candidates": [context.candidate, context.candidate]}
    suggested = {**context.candidate, "name": "Official name"}
    failure = {
        "status": "timeout", "failed_step": "uses_translation",
        "retry_token": "signed-token", "suggested_candidate": suggested,
    }
    context.api.send_selection_or_retry.return_value = failure

    async def select():
        await context.session.identify(b"photo")
        return await context.session.select_match(0)

    assert asyncio.run(select()) == failure
    assert context.session.result["suggested_candidate"] == suggested


@pytest.mark.parametrize("status_code", [422, 429])
def test_non_server_api_errors_are_not_recoverable_connection_errors(identification, status_code):
    context = identification
    context.api.identify.return_value = {
        "status": "multiple_matches", "presentations": [context.medication, context.medication]
    }
    context.api.send_selection_or_retry.side_effect = ApiError("Request failed", status_code=status_code)

    async def select():
        await context.session.identify(b"photo")
        with pytest.raises(ApiError, match="Request failed") as error:
            await context.session.select_match(0)
        assert error.value.status_code == status_code

    asyncio.run(select())
    assert context.session.result is None
    assert not context.session.can_retry
    assert not context.session.is_running
    assert context.session.photo == b"photo"
    assert context.api.identify.await_count == 1
