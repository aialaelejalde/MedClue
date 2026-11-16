"""Test the cancellation action while identification is in progress."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from medclue_mobile.ui.screens.identifying_medication import IdentifyingMedicationScreen


ASYNC_OPERATION_TIMEOUT_SECONDS = 5


@pytest.mark.parametrize("outcome", ["success", "error", "cancelled"])
def test_pending_cancellation_blocks_repeated_clicks_and_releases_the_button(outcome):
    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def wait_for_cancellation():
            started.set()
            await release.wait()
            if outcome == "error":
                raise RuntimeError("Navigation failed")

        cancel = AsyncMock(side_effect=wait_for_cancellation)
        screen = IdentifyingMedicationScreen(cancel)
        task = asyncio.create_task(screen._cancel_button.on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            assert screen._cancel_button.disabled
            await screen._cancel_button.on_click(None)
            cancel.assert_awaited_once_with()
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

        assert not screen._cancel_button.disabled
        cancel.side_effect = None
        await screen._cancel_button.on_click(None)
        assert cancel.await_count == 2

    asyncio.run(run())
