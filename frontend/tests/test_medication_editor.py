"""Test adding and editing behavior."""

import asyncio
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest

from medclue_mobile.cabinet import DuplicateMedicationError, MedicationCabinet
from medclue_mobile.medications import Medication
from medclue_mobile.photos import CameraPermissionError
from medclue_mobile.ui.screens import medication_editor
from medclue_mobile.ui.screens.medication_editor import MedicationEditorScreen


@pytest.fixture(params=["add", "edit"])
def editor_context(request, monkeypatch):
    page = SimpleNamespace()
    monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
    error = AsyncMock(return_value=False)
    duplicate = AsyncMock(return_value=False)
    success = Mock()
    compress = Mock(return_value=b"compressed photo")
    monkeypatch.setattr(medication_editor, "show_error", error)
    monkeypatch.setattr(medication_editor, "confirm_duplicate", duplicate)
    monkeypatch.setattr(medication_editor, "show_save_success", success)
    monkeypatch.setattr(medication_editor, "compress_photo", compress)

    original = Medication(
        name="Original name", photo=b"original photo",
        id=7 if request.param == "edit" else None,
    )
    cabinet = Mock(spec=MedicationCabinet)
    cabinet.save_medication.side_effect = lambda draft, **kwargs: replace(draft, id=7)
    saved = AsyncMock()
    take_photo = AsyncMock()
    screen = MedicationEditorScreen(
        cabinet, saved, mode=request.param, medication=original, on_take_photo=take_photo,
    )
    return SimpleNamespace(
        screen=screen, original=original, cabinet=cabinet, saved=saved,
        take_photo=take_photo, error=error, duplicate=duplicate, success=success,
        compress=compress, mode=request.param, page=page,
    )


@pytest.mark.parametrize("mode,medication,message", [
    ("add", Medication(name="Saved", id=7), "without saved metadata"),
    ("add", Medication(name="Saved", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)), "without saved metadata"),
    ("edit", None, "A medication record is required"),
    ("edit", Medication(name="Unsaved"), "requires a saved record"),
    ("edit", Medication(id=7), "at least one piece of information"),
])
def test_editor_rejects_initial_records_that_do_not_fit_the_mode(mode, medication, message):
    with pytest.raises(ValueError, match=message):
        MedicationEditorScreen(Mock(spec=MedicationCabinet), AsyncMock(), mode=mode, medication=medication)


def test_invalid_form_is_kept_without_saving(editor_context):
    context = editor_context
    context.screen.form.set_photo(None)
    context.screen.form.name_field.value = ""

    asyncio.run(context.screen._save_button.on_click(None))

    context.error.assert_awaited_once_with(
        context.page, "Cannot save medication", "Please add at least one piece of information before saving.",
    )
    context.cabinet.save_medication.assert_not_called()
    context.saved.assert_not_awaited()
    assert context.screen.form.name_field.value == ""
    assert not context.screen.form.disabled
    assert not context.screen._save_button.disabled


@pytest.mark.parametrize("field,message", [
    ("amount", "Quantity must contain a valid number."),
    ("frequency", "Frequency interval must contain a valid number."),
])
def test_invalid_numbers_keep_the_input_available_for_correction(editor_context, field, message):
    context = editor_context
    form = context.screen.form
    if field == "amount":
        form.amount_unit.value = "tablets"
    else:
        form.frequency_type.value = "interval"
        form.frequency_type.on_select(None)
        form.frequency_unit.value = "hours"
    control = getattr(form, f"{field}_value")
    control.value = "unfinished number"

    asyncio.run(context.screen._save_button.on_click(None))

    context.error.assert_awaited_once_with(context.page, "Cannot save medication", message)
    context.cabinet.save_medication.assert_not_called()
    context.saved.assert_not_awaited()
    context.compress.assert_not_called()
    assert control.value == "unfinished number"
    assert not form.disabled
    assert not context.screen._save_button.disabled


@pytest.mark.parametrize("photo", [None, b"original photo", b"replacement photo"])
def test_save_prepares_only_the_photos_required_by_the_mode(editor_context, photo):
    context = editor_context
    context.screen.form.set_photo(photo)

    asyncio.run(context.screen._save_button.on_click(None))

    needs_compression = photo is not None and (context.mode == "add" or photo != context.original.photo)
    draft = context.cabinet.save_medication.call_args.args[0]
    assert draft.photo == (b"compressed photo" if needs_compression else photo)
    if needs_compression:
        context.compress.assert_called_once_with(photo)
    else:
        context.compress.assert_not_called()
    assert context.screen.form.get_medication().photo == photo
    assert context.original.photo == b"original photo"
    assert draft.id == context.original.id
    context.saved.assert_awaited_once_with(replace(draft, id=7))


def test_compression_error_keeps_the_form_without_saving(editor_context):
    context = editor_context
    context.screen.form.set_photo(b"replacement photo")
    context.compress.side_effect = ValueError("The photo could not be prepared for saving.")

    asyncio.run(context.screen._save_button.on_click(None))

    context.error.assert_awaited_once_with(
        context.page, "Cannot save medication", "The photo could not be prepared for saving.",
    )
    context.cabinet.save_medication.assert_not_called()
    context.saved.assert_not_awaited()
    assert context.screen.form.get_medication().photo == b"replacement photo"
    assert not context.screen._save_button.disabled


@pytest.mark.parametrize("confirm", [False, True])
def test_duplicate_is_saved_only_after_confirmation(editor_context, confirm):
    context = editor_context
    context.screen.form.name_field.value = "Duplicate name"
    saved = Medication(name="Duplicate name", id=7)
    context.cabinet.save_medication.side_effect = [DuplicateMedicationError(), saved]
    context.duplicate.return_value = confirm

    asyncio.run(context.screen._save_button.on_click(None))

    context.duplicate.assert_awaited_once_with(context.page)
    assert [item.kwargs["allow_duplicate"] for item in context.cabinet.save_medication.call_args_list] == (
        [False, True] if confirm else [False]
    )
    if confirm:
        context.saved.assert_awaited_once_with(saved)
    else:
        context.saved.assert_not_awaited()
        assert context.screen.form.name_field.value == "Duplicate name"
        assert not context.screen._save_button.disabled


@pytest.mark.parametrize("retry", [False, True])
def test_storage_error_respects_retry_and_keeps_the_prepared_draft(editor_context, retry):
    context = editor_context
    context.screen.form.set_photo(b"replacement photo")
    context.cabinet.save_medication.side_effect = [sqlite3.OperationalError("unavailable"), Medication(id=7, name="Saved")]
    context.error.return_value = retry

    asyncio.run(context.screen._save_button.on_click(None))

    message = "We couldn't save your changes. Please try again." if context.mode == "edit" else (
        "We couldn't save this medication. Please try again."
    )
    assert context.error.await_args.args == (context.page, "Cannot save medication", message)
    assert context.error.await_args.kwargs["action_text"] == "Try again"
    context.compress.assert_called_once_with(b"replacement photo")
    attempts = context.cabinet.save_medication.call_args_list
    assert len(attempts) == (2 if retry else 1)
    if retry:
        assert attempts[0] == attempts[1]
        context.saved.assert_awaited_once()
    else:
        context.saved.assert_not_awaited()
        assert context.screen.form.get_medication().photo == b"replacement photo"
        assert not context.screen._save_button.disabled


def test_retry_keeps_duplicate_consent(editor_context):
    context = editor_context
    saved = Medication(name="Saved", id=7)
    context.cabinet.save_medication.side_effect = [
        DuplicateMedicationError(), sqlite3.OperationalError("unavailable"), saved,
    ]
    context.duplicate.return_value = True
    context.error.return_value = True

    asyncio.run(context.screen._save_button.on_click(None))

    context.duplicate.assert_awaited_once()
    assert [item.kwargs["allow_duplicate"] for item in context.cabinet.save_medication.call_args_list] == [False, True, True]
    context.saved.assert_awaited_once_with(saved)


def test_missing_record_is_handled_only_when_editing(editor_context):
    context = editor_context
    context.cabinet.save_medication.side_effect = LookupError("Record not found")

    if context.mode == "edit":
        asyncio.run(context.screen._save_button.on_click(None))
        context.error.assert_awaited_once()
    else:
        with pytest.raises(LookupError, match="Record not found"):
            asyncio.run(context.screen._save_button.on_click(None))
        context.error.assert_not_awaited()
    context.saved.assert_not_awaited()
    assert not context.screen._save_button.disabled


@pytest.mark.parametrize("photo", [None, b"new photo"])
def test_photo_capture_changes_the_form_only_when_a_photo_is_returned(editor_context, photo):
    context = editor_context
    context.take_photo.return_value = photo

    asyncio.run(context.screen._take_photo(None))

    assert context.screen.form.get_medication().photo == (photo if photo is not None else context.original.photo)
    assert context.screen.form.has_changes() is (photo is not None)
    context.cabinet.save_medication.assert_not_called()
    context.error.assert_not_awaited()
    assert not context.screen.form.disabled


@pytest.mark.parametrize("error", [CameraPermissionError(), OSError(), ValueError(), RuntimeError()])
def test_photo_error_keeps_the_previous_photo_and_shows_the_current_message(editor_context, error):
    context = editor_context
    context.take_photo.side_effect = error

    asyncio.run(context.screen._take_photo(None))

    if isinstance(error, CameraPermissionError):
        title = "Camera access is off"
        message = "You can edit the medication without changing its photo." if context.mode == "edit" else (
            "You can add the medication without a photo."
        )
    else:
        title, message = "Could not take photo", "Please try again."
    context.error.assert_awaited_once_with(context.page, title, message)
    assert context.screen.form.get_medication().photo == context.original.photo
    assert not context.screen.form.has_changes()
    assert not context.screen._save_button.disabled


@pytest.mark.parametrize("operation", ["save", "photo"])
def test_pending_operation_blocks_actions_and_leaving_until_cancelled(editor_context, monkeypatch, operation):
    context = editor_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def wait_for_operation(*args):
            started.set()
            await release.wait()

        context.take_photo.side_effect = wait_for_operation
        compression = AsyncMock(side_effect=wait_for_operation)
        monkeypatch.setattr(medication_editor.asyncio, "to_thread", compression)
        context.screen.form.set_photo(b"replacement photo")
        action = context.screen._save_button.on_click if operation == "save" else context.screen._take_photo
        task = asyncio.create_task(action(None))
        try:
            await started.wait()
            assert context.screen.form.disabled
            assert context.screen._save_button.disabled
            assert not await context.screen.can_leave()
            await context.screen._save_button.on_click(None)
            await context.screen._take_photo(None)
            context.cabinet.save_medication.assert_not_called()
            assert context.take_photo.await_count == (1 if operation == "photo" else 0)
            assert compression.await_count == (1 if operation == "save" else 0)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not context.screen.form.disabled
        assert not context.screen._save_button.disabled

    asyncio.run(run())


def test_successful_save_prevents_further_actions_and_preserves_control_states(editor_context):
    context = editor_context

    async def run():
        await context.screen._save_button.on_click(None)
        assert await context.screen.can_leave()
        await context.screen._save_button.on_click(None)
        await context.screen._take_photo(None)

    asyncio.run(run())

    context.cabinet.save_medication.assert_called_once()
    context.saved.assert_awaited_once()
    context.success.assert_called_once_with(context.page)
    context.take_photo.assert_not_awaited()
    assert context.screen._save_button.disabled
    assert context.screen.form.disabled is (context.mode == "edit")
