"""Test the camera dialog result, errors, and cleanup."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest

from medclue_mobile.photos import CameraPermissionError
from medclue_mobile.ui import photo_capture
from medclue_mobile.ui.photo_capture import PhotoCaptureDialog


ASYNC_OPERATION_TIMEOUT_SECONDS = 5


@pytest.fixture
def capture_context(monkeypatch):
    shown = asyncio.Event()
    page = SimpleNamespace(width=390)

    def show(dialog):
        dialog.open = True
        page.dialog = dialog
        shown.set()

    def pop():
        page.dialog.open = False

    page.show_dialog = Mock(side_effect=show)
    page.pop_dialog = Mock(side_effect=pop)
    photos = SimpleNamespace(
        camera=ft.Container(), initialize_camera=AsyncMock(),
        capture=AsyncMock(return_value=b"new photo"), discard_photo=Mock(),
    )
    error = AsyncMock()
    update = Mock()
    monkeypatch.setattr(photo_capture, "PhotoManager", lambda: photos)
    monkeypatch.setattr(photo_capture, "show_error", error)
    monkeypatch.setattr(ft.Control, "update", update)
    return SimpleNamespace(page=page, photos=photos, error=error, update=update, shown=shown)


async def open_capture(context):
    capture = PhotoCaptureDialog(context.page)
    task = asyncio.create_task(capture.open())
    await asyncio.wait_for(context.shown.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
    return capture, task


@pytest.mark.parametrize("action", ["capture", "cancel", "dismiss"])
def test_photo_dialog_returns_result_and_cleans_up(capture_context, action):
    context = capture_context

    async def run():
        capture, task = await open_capture(context)
        try:
            if action == "capture":
                await capture._take_button.on_click(None)
                context.photos.capture.assert_awaited_once_with()
            elif action == "cancel":
                capture._cancel(None)
            else:
                capture._dialog.on_dismiss(None)
            assert await task == (b"new photo" if action == "capture" else None)
            if action != "capture":
                context.photos.capture.assert_not_awaited()
            context.photos.discard_photo.assert_called_once_with()
            context.page.pop_dialog.assert_called_once_with()
        finally:
            capture.close()
            await task

    asyncio.run(run())


def test_preview_events_after_the_dialog_ends_do_not_update_controls(capture_context, monkeypatch):
    context = capture_context
    fit = Mock()
    monkeypatch.setattr(photo_capture, "fit_camera_preview", fit)

    async def run():
        capture, task = await open_capture(context)
        capture._dialog.on_dismiss(None)
        await task
        context.update.reset_mock()

        capture._resize_preview(SimpleNamespace(width=280, height=210))
        context.photos.camera.on_state_change(SimpleNamespace(
            aspect_ratio=16 / 9, device_orientation=ft.DeviceOrientation.LANDSCAPE_LEFT,
            locked_capture_orientation=None, preview_pause_orientation=None,
        ))

        fit.assert_not_called()
        context.update.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("error", [CameraPermissionError("Permission denied"), RuntimeError("Camera unavailable")])
def test_initialization_failure_keeps_its_error_handling_and_cleans_up(capture_context, error):
    context = capture_context
    context.photos.initialize_camera.side_effect = error

    async def run():
        capture = PhotoCaptureDialog(context.page)
        if isinstance(error, CameraPermissionError):
            with pytest.raises(CameraPermissionError):
                await capture.open()
            context.error.assert_not_awaited()
        else:
            assert await capture.open() is None
            context.error.assert_awaited_once_with(
                context.page, "Could not take photo", "We couldn't start the camera. Please try again.",
            )
        context.photos.discard_photo.assert_called_once_with()
        context.page.pop_dialog.assert_called_once_with()

    asyncio.run(run())


def test_capture_failure_allows_another_attempt_in_the_same_dialog(capture_context):
    context = capture_context
    context.photos.capture.side_effect = [OSError("Capture failed"), b"new photo"]

    async def run():
        capture, task = await open_capture(context)
        try:
            await capture._take_button.on_click(None)
            context.error.assert_awaited_once_with(context.page, "Could not take photo", "Please try again.")
            assert not task.done()
            assert not capture._take_button.disabled
            context.photos.discard_photo.assert_not_called()

            await capture._take_button.on_click(None)
            assert await task == b"new photo"
            context.photos.discard_photo.assert_called_once_with()
        finally:
            capture.close()
            await task

    asyncio.run(run())


@pytest.mark.parametrize("action", ["cancel", "close"])
@pytest.mark.parametrize("late_error", [False, True])
def test_pending_capture_blocks_repeated_clicks_and_ignores_completion_after_exit(capture_context, action, late_error):
    context = capture_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_photo():
            started.set()
            await release.wait()
            if late_error:
                raise OSError("Late capture error")
            return b"late photo"

        context.photos.capture.side_effect = delayed_photo
        capture, task = await open_capture(context)
        capture_task = asyncio.create_task(capture._take_button.on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            assert capture._take_button.disabled
            await capture._take_button.on_click(None)
            context.photos.capture.assert_awaited_once_with()
            if action == "cancel":
                capture._cancel(None)
            else:
                capture.close()
            assert await task is None
            context.photos.discard_photo.assert_called_once_with()
            context.update.reset_mock()
            context.page.pop_dialog.reset_mock()
        finally:
            capture.close()
            release.set()
            await capture_task
            await task
        context.error.assert_not_awaited()
        context.update.assert_not_called()
        context.page.pop_dialog.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("late_error", [None, CameraPermissionError("Permission denied"), RuntimeError("Camera unavailable")])
def test_close_during_initialization_ignores_late_completion(capture_context, late_error):
    context = capture_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def initialize():
            started.set()
            await release.wait()
            if late_error is not None:
                raise late_error

        context.photos.initialize_camera.side_effect = initialize
        capture, task = await open_capture(context)
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            capture.close()
        finally:
            capture.close()
            release.set()
        assert await task is None
        context.photos.discard_photo.assert_called_once_with()
        context.error.assert_not_awaited()
        context.update.assert_not_called()
        context.page.pop_dialog.assert_not_called()

    asyncio.run(run())


def test_cancelling_the_dialog_task_discards_the_photo_and_removes_the_dialog(capture_context):
    context = capture_context

    async def run():
        capture, task = await open_capture(context)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        context.photos.discard_photo.assert_called_once_with()
        context.page.pop_dialog.assert_called_once_with()

    asyncio.run(run())
