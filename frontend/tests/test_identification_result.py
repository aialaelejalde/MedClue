"""Test confirmed identification result actions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from medclue_mobile.medications import Medication
from medclue_mobile.ui.screens.identification_result import IdentificationResultScreen


ASYNC_OPERATION_TIMEOUT_SECONDS = 5


@pytest.fixture
def result_context():
    result = {
        "status": "verified",
        "medication": {"name": "Confirmed medication", "strength": "500 mg", "form": "tablet"},
        "official_uses": ["Official use", "Another use"],
    }
    save = AsyncMock()
    identify = AsyncMock()
    screen = IdentificationResultScreen(result, b"captured photo", save, identify)
    return SimpleNamespace(screen=screen, save=save, identify=identify)


@pytest.mark.parametrize("official_uses", [[], ["Official use", "Another use"]])
def test_save_passes_confirmed_medication_and_available_uses(official_uses):
    save = AsyncMock()
    screen = IdentificationResultScreen(
        {
            "status": "verified",
            "medication": {"name": "Confirmed medication", "strength": "500 mg", "form": "tablet"},
            "official_uses": official_uses,
        },
        b"captured photo", save, AsyncMock(),
    )

    asyncio.run(screen._save_button.on_click(None))

    save.assert_awaited_once_with(
        Medication(name="Confirmed medication", strength="500 mg", form="tablet", photo=b"captured photo"),
        official_uses,
    )


def test_identify_another_medication_calls_its_callback(result_context):
    asyncio.run(result_context.screen._identify_button.on_click(None))

    result_context.identify.assert_awaited_once_with()
    result_context.save.assert_not_awaited()


@pytest.mark.parametrize("step", ["official_uses_retrieval", "uses_translation"])
def test_unavailable_uses_show_notice_and_allow_retry_or_save(step):
    retry = AsyncMock()
    save = AsyncMock()
    screen = IdentificationResultScreen(
        {"status": "verified", "medication": {"name": "Confirmed medication"},
         "official_uses": [], "failed_step": step, "retry_token": "signed-token"},
        b"photo", save, AsyncMock(), on_retry=retry,
    )
    information = screen.content.content.controls[0].content.controls[0].content.controls
    assert "couldn't retrieve its official uses" in information[-1].value
    assert screen._retry_button.visible
    asyncio.run(screen._retry_button.on_click(None))
    retry.assert_awaited_once_with()
    asyncio.run(screen._save_button.on_click(None))
    save.assert_awaited_once_with(Medication(name="Confirmed medication", photo=b"photo"), [])


def test_successfully_empty_uses_do_not_offer_retry():
    screen = IdentificationResultScreen(
        {"status": "verified", "medication": {"name": "Confirmed medication"}, "official_uses": []},
        b"photo", AsyncMock(), AsyncMock(), on_retry=AsyncMock(),
    )
    assert not screen._retry_button.visible


def test_pending_uses_retry_blocks_other_actions():
    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def retry():
            started.set()
            await release.wait()

        callback = AsyncMock(side_effect=retry)
        save, identify = AsyncMock(), AsyncMock()
        screen = IdentificationResultScreen(
            {"status": "verified", "medication": {"name": "Confirmed medication"},
             "failed_step": "uses_translation", "retry_token": "signed-token"},
            b"photo", save, identify, on_retry=callback,
        )
        task = asyncio.create_task(screen._retry_button.on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            assert screen._save_button.disabled
            assert screen._identify_button.disabled
            assert screen._retry_button.disabled
            await screen._retry_button.on_click(None)
            await screen._save_button.on_click(None)
            await screen._identify_button.on_click(None)
            callback.assert_awaited_once_with()
            save.assert_not_awaited()
            identify.assert_not_awaited()
        finally:
            release.set()
            await task
        assert not screen._retry_button.disabled

    asyncio.run(run())


@pytest.mark.parametrize("action", ["save", "identify"])
@pytest.mark.parametrize("outcome", ["success", "error", "cancelled"])
def test_pending_action_blocks_both_buttons_and_releases_them(result_context, action, outcome):
    context = result_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def wait_for_action(*args):
            started.set()
            await release.wait()
            if outcome == "error":
                raise RuntimeError("Navigation failed")

        callback = context.save if action == "save" else context.identify
        button = context.screen._save_button if action == "save" else context.screen._identify_button
        callback.side_effect = wait_for_action
        task = asyncio.create_task(button.on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            assert context.screen._save_button.disabled
            assert context.screen._identify_button.disabled
            await context.screen._save_button.on_click(None)
            await context.screen._identify_button.on_click(None)
            assert context.save.await_count == (1 if action == "save" else 0)
            assert context.identify.await_count == (1 if action == "identify" else 0)
        finally:
            release.set()
            if outcome == "cancelled":
                task.cancel()
            if outcome == "success":
                await task
            else:
                error = RuntimeError if outcome == "error" else asyncio.CancelledError
                with pytest.raises(error):
                    await task

        assert not context.screen._save_button.disabled
        assert not context.screen._identify_button.disabled
        callback.side_effect = None
        await button.on_click(None)
        assert callback.await_count == 2

    asyncio.run(run())
