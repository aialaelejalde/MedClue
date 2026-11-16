"""Test provisional identification results and their available actions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import flet as ft
import pytest

from medclue_mobile.medications import Medication
from medclue_mobile.ui.screens.possible_match_result import PossibleMatchResultScreen


ASYNC_OPERATION_TIMEOUT_SECONDS = 5
SUGGESTED_CANDIDATE = {"name": "Suggested", "strength": "100 mg", "form": "Comprimidos recubiertos"}
RESULTS = [
    {"status": "not_identified"},
    {"status": "no_match", "suggested_candidate": SUGGESTED_CANDIDATE},
    {"status": "connection_error", "failed_step": "image_analysis"},
    {"status": "connection_error", "failed_step": "cima_verification", "suggested_candidate": SUGGESTED_CANDIDATE},
    {"status": "timeout", "failed_step": "image_analysis"},
    {
        "status": "timeout", "failed_step": "cima_verification",
        "suggested_candidate": {"name": "Suggested", "strength": None, "form": "Comprimidos recubiertos"},
    },
]


def result_context(result):
    retry = AsyncMock()
    retake = AsyncMock()
    add = AsyncMock()
    screen = PossibleMatchResultScreen(result, b"captured photo", retry, retake, add)
    return SimpleNamespace(screen=screen, retry=retry, retake=retake, add=add)


def displayed_text(control):
    if isinstance(control, ft.Text):
        yield control.value
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from displayed_text(content)
    for child in getattr(control, "controls", []):
        yield from displayed_text(child)


@pytest.mark.parametrize("result", RESULTS)
def test_retry_is_available_only_for_retryable_results(result):
    context = result_context(result)

    asyncio.run(context.screen._retry_button.on_click(None))

    if result["status"] == "no_match":
        assert not context.screen._retry_button.visible
        context.retry.assert_not_awaited()
    else:
        assert context.screen._retry_button.visible
        context.retry.assert_awaited_once_with()
    context.retake.assert_not_awaited()
    context.add.assert_not_awaited()


def test_retake_calls_its_callback():
    context = result_context({"status": "not_identified"})

    asyncio.run(context.screen._retake_button.on_click(None))

    context.retake.assert_awaited_once_with()
    context.retry.assert_not_awaited()
    context.add.assert_not_awaited()


@pytest.mark.parametrize("result", RESULTS)
def test_manual_add_keeps_available_details_and_photo_without_official_uses(result):
    context = result_context(result)

    asyncio.run(context.screen._add_button.on_click(None))

    expected = Medication(photo=b"captured photo", **(result.get("suggested_candidate") or {}))
    context.add.assert_awaited_once_with(expected)
    context.retry.assert_not_awaited()
    context.retake.assert_not_awaited()


@pytest.mark.parametrize("result", RESULTS)
def test_result_shows_available_suggestion_as_unconfirmed(result):
    context = result_context(result)

    text = list(displayed_text(context.screen))

    if result.get("suggested_candidate"):
        candidate = result["suggested_candidate"]
        assert "Possible match" in text
        assert candidate["name"] in text
        description = " · ".join(candidate[field] for field in ("strength", "form") if candidate.get(field))
        assert description in text
        assert "Not identified" not in text
    else:
        assert "Not identified" in text
        assert "Possible match" not in text
    assert "Identified" not in text


@pytest.mark.parametrize("action", ["retry", "retake", "add"])
@pytest.mark.parametrize("outcome", ["success", "error", "cancelled"])
def test_pending_action_blocks_other_actions_and_releases_them(action, outcome):
    context = result_context({"status": "timeout", "failed_step": "cima_verification"})

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def wait_for_action(*args):
            started.set()
            await release.wait()
            if outcome == "error":
                raise RuntimeError("Navigation failed")

        buttons = {
            "retry": context.screen._retry_button,
            "retake": context.screen._retake_button,
            "add": context.screen._add_button,
        }
        callback = getattr(context, action)
        callback.side_effect = wait_for_action
        task = asyncio.create_task(buttons[action].on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            for button in buttons.values():
                assert button.disabled
                await button.on_click(None)
            for name in buttons:
                assert getattr(context, name).await_count == (1 if name == action else 0)
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

        assert all(not button.disabled for button in buttons.values())
        callback.side_effect = None
        await buttons[action].on_click(None)
        assert callback.await_count == 2

    asyncio.run(run())
