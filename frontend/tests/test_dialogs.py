"""Test dialog decisions, cancellation, and the deletion workflow."""

import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from medclue_mobile.ui import dialogs


ASYNC_OPERATION_TIMEOUT_SECONDS = 5


@pytest.fixture
def page():
    opened = []

    def show(dialog):
        dialog.open = True
        opened.append(dialog)

    def close():
        opened[-1].open = False

    return SimpleNamespace(show_dialog=Mock(side_effect=show), pop_dialog=Mock(side_effect=close))


async def open_dialog(page, operation):
    task = asyncio.create_task(operation)
    await asyncio.sleep(0)
    return task, page.show_dialog.call_args.args[0]


@pytest.mark.parametrize("choice", ["confirm", "cancel", "dismiss"])
@pytest.mark.parametrize("confirmation,title", [
    (dialogs.confirm_discard_changes, "Discard changes?"),
    (dialogs.confirm_duplicate, "Possible duplicate"),
    (dialogs.confirm_leave_identification, "Leave identification?"),
])
def test_confirmation_returns_true_only_for_the_confirm_action(page, choice, confirmation, title):
    async def run():
        task, dialog = await open_dialog(page, confirmation(page))
        assert dialog.title.value == title
        if choice == "confirm":
            dialog.actions[-1].on_click()
        elif choice == "cancel":
            dialog.actions[0].on_click()
        else:
            dialog.on_dismiss(None)

        assert await asyncio.wait_for(task, timeout=ASYNC_OPERATION_TIMEOUT_SECONDS) is (choice == "confirm")
        assert not dialog.open

    asyncio.run(run())


@pytest.mark.parametrize("retake", [False, True])
def test_oversized_photo_returns_whether_the_user_wants_to_retake_it(page, retake):
    async def run():
        task, dialog = await open_dialog(page, dialogs.show_photo_too_large(page))
        assert dialog.title.value == "Photo is too large"
        assert dialog.content.value == "This photo is over 15 MB. Please take another photo."
        assert dialog.actions[-1].content == "Retake photo"
        if retake:
            dialog.actions[-1].on_click()
        else:
            dialog.on_dismiss(None)

        assert await asyncio.wait_for(task, timeout=ASYNC_OPERATION_TIMEOUT_SECONDS) is retake
        assert not dialog.open

    asyncio.run(run())


@pytest.mark.parametrize("accept", [False, True])
def test_error_dialog_distinguishes_the_action_from_dismissal(page, accept):
    async def run():
        task, dialog = await open_dialog(page, dialogs.show_error(page, "Operation failed", "Please try again."))
        if accept:
            dialog.actions[-1].on_click()
        else:
            dialog.on_dismiss(None)

        assert await asyncio.wait_for(task, timeout=ASYNC_OPERATION_TIMEOUT_SECONDS) is accept
        assert not dialog.open

    asyncio.run(run())


def test_cancelling_the_waiting_task_closes_the_dialog(page):
    async def run():
        task, dialog = await open_dialog(page, dialogs.confirm_discard_changes(page))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not dialog.open

    asyncio.run(run())


def test_repeated_actions_keep_the_first_choice_and_close_only_once(page):
    async def run():
        task, dialog = await open_dialog(page, dialogs.confirm_discard_changes(page))
        dialog.actions[-1].on_click()
        dialog.actions[0].on_click()
        dialog.on_dismiss(None)

        assert await asyncio.wait_for(task, timeout=ASYNC_OPERATION_TIMEOUT_SECONDS) is True
        page.pop_dialog.assert_called_once_with()

    asyncio.run(run())


@pytest.mark.parametrize("retry", [False, True])
def test_failed_delete_retries_only_with_user_consent(page, retry):
    delete = Mock(side_effect=[sqlite3.OperationalError("unavailable"), None])

    async def run():
        task, confirmation = await open_dialog(page, dialogs.delete_medication_with_confirmation(page, delete))
        confirmation.actions[-1].on_click()
        await asyncio.sleep(0)
        error = page.show_dialog.call_args.args[0]
        assert error.title.value == "Cannot delete medication"
        assert error.content.value == "We couldn't delete this medication. Please try again."
        if retry:
            error.actions[-1].on_click()
        else:
            error.on_dismiss(None)

        assert await asyncio.wait_for(task, timeout=ASYNC_OPERATION_TIMEOUT_SECONDS) is retry

    asyncio.run(run())

    assert delete.call_count == (2 if retry else 1)


def test_rejected_delete_confirmation_does_not_delete(page):
    delete = Mock()

    async def run():
        task, confirmation = await open_dialog(page, dialogs.delete_medication_with_confirmation(page, delete))
        confirmation.actions[0].on_click()

        assert await asyncio.wait_for(task, timeout=ASYNC_OPERATION_TIMEOUT_SECONDS) is False

    asyncio.run(run())

    delete.assert_not_called()
