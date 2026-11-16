"""Test possible match selection and alternative actions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from medclue_mobile.medications import Medication
from medclue_mobile.ui.screens.possible_matches import PossibleMatchesScreen


ASYNC_OPERATION_TIMEOUT_SECONDS = 5
OPTIONS = [
    {"name": "First medication", "strength": "100 mg", "form": "tablet", "national_code": "1"},
    {"name": "Second medication", "strength": "200 mg", "form": "capsule", "national_code": "2"},
]


@pytest.fixture
def matches_context():
    select = AsyncMock()
    retake = AsyncMock()
    add = AsyncMock()
    screen = PossibleMatchesScreen(
        {"status": "multiple_matches", "candidates": OPTIONS},
        b"captured photo", select, retake, add,
    )
    return SimpleNamespace(screen=screen, select=select, retake=retake, add=add)


@pytest.mark.parametrize("option_type", ["candidates", "presentations"])
@pytest.mark.parametrize("index", [0, 1])
def test_selecting_an_option_passes_its_index(option_type, index):
    select = AsyncMock()
    screen = PossibleMatchesScreen(
        {"status": "multiple_matches", option_type: OPTIONS},
        b"captured photo", select, AsyncMock(), AsyncMock(),
    )
    select.assert_not_awaited()

    asyncio.run(screen._match_list.controls[index].on_click(None))

    select.assert_awaited_once_with(index)


def test_retake_calls_its_callback(matches_context):
    asyncio.run(matches_context.screen._retake_button.on_click(None))

    matches_context.retake.assert_awaited_once_with()
    matches_context.select.assert_not_awaited()
    matches_context.add.assert_not_awaited()


@pytest.mark.parametrize("option_type,suggestion", [
    ("candidates", None),
    ("presentations", None),
    ("presentations", {"name": "Suggested medication", "strength": "100 mg", "form": "tablet"}),
])
def test_manual_add_keeps_photo_and_only_the_existing_suggestion(option_type, suggestion):
    select = AsyncMock()
    add = AsyncMock()
    screen = PossibleMatchesScreen(
        {"status": "multiple_matches", option_type: OPTIONS, "suggested_candidate": suggestion},
        b"captured photo", select, AsyncMock(), add,
    )

    asyncio.run(screen._add_button.on_click(None))

    add.assert_awaited_once_with(Medication(photo=b"captured photo", **(suggestion or {})))
    select.assert_not_awaited()


@pytest.mark.parametrize("action", ["select", "retake", "add"])
@pytest.mark.parametrize("outcome", ["success", "error", "cancelled"])
def test_pending_action_blocks_other_actions_and_releases_them(matches_context, action, outcome):
    context = matches_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def wait_for_action(*args):
            started.set()
            await release.wait()
            if outcome == "error":
                raise RuntimeError("Navigation failed")

        buttons = {
            "select": context.screen._match_list.controls[0],
            "retake": context.screen._retake_button,
            "add": context.screen._add_button,
        }
        callback = getattr(context, action)
        callback.side_effect = wait_for_action
        task = asyncio.create_task(buttons[action].on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            for card in context.screen._match_list.controls:
                assert card.disabled
                await card.on_click(None)
            assert context.screen._retake_button.disabled
            assert context.screen._add_button.disabled
            await context.screen._retake_button.on_click(None)
            await context.screen._add_button.on_click(None)
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

        assert not context.screen._match_list.disabled
        assert all(not card.disabled for card in context.screen._match_list.controls)
        assert not context.screen._retake_button.disabled
        assert not context.screen._add_button.disabled
        callback.side_effect = None
        await buttons[action].on_click(None)
        assert callback.await_count == 2

    asyncio.run(run())
