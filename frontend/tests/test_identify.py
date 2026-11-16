"""Test camera readiness, capture, errors, and the identification screen lifecycle."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest

from medclue_mobile.api_client import PhotoTooLargeError
from medclue_mobile.photos import CameraPermissionError, PhotoManager
from medclue_mobile.ui.screens import identify
from medclue_mobile.ui.screens.identify import IdentifyScreen


ASYNC_OPERATION_TIMEOUT_SECONDS = 5


@pytest.fixture
def camera_context(monkeypatch):
    page = SimpleNamespace(run_task=Mock(side_effect=lambda function: asyncio.create_task(function())))
    monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
    photos = Mock(spec=PhotoManager)
    photos.camera = ft.Container()
    photos.camera.update = Mock()
    photos.capture.return_value = b"captured photo"
    photos.media_type = "image/jpeg"
    on_identify = AsyncMock()
    error = AsyncMock()
    too_large = AsyncMock()
    monkeypatch.setattr(identify, "show_error", error)
    monkeypatch.setattr(identify, "show_photo_too_large", too_large)
    screen = IdentifyScreen(photos, on_identify)
    return SimpleNamespace(
        screen=screen, photos=photos, on_identify=on_identify,
        error=error, too_large=too_large, page=page,
    )


async def mount_screen(context):
    context.screen.did_mount()
    await context.screen._camera_task


def test_ready_camera_sends_the_captured_photo_and_media_type(camera_context):
    context = camera_context

    async def run():
        assert context.screen._identify_button.disabled
        await mount_screen(context)
        assert not context.screen._identify_button.disabled
        await context.screen._identify_button.on_click(None)

    asyncio.run(run())

    context.photos.initialize_camera.assert_awaited_once_with()
    context.photos.capture.assert_awaited_once_with(for_identification=True)
    context.on_identify.assert_awaited_once_with(b"captured photo", "image/jpeg")
    context.error.assert_not_awaited()


@pytest.mark.parametrize("stage", ["initialization", "capture"])
def test_denied_permission_prevents_identification_and_keeps_the_current_message(camera_context, stage):
    context = camera_context

    async def run():
        if stage == "initialization":
            context.photos.initialize_camera.side_effect = CameraPermissionError()
        await mount_screen(context)
        if stage == "capture":
            context.photos.capture.side_effect = CameraPermissionError()
            await context.screen._identify_button.on_click(None)

    asyncio.run(run())

    assert context.screen._status_title.value == "Camera access is off"
    assert context.screen._status_message.value == "Allow camera access in Settings to take photos."
    assert context.screen._status_panel.visible
    assert not context.screen._status_action.visible
    assert context.screen._identify_button.disabled
    context.on_identify.assert_not_awaited()


@pytest.mark.parametrize("error", [OSError(), ValueError(), RuntimeError(), ft.FletException()])
def test_camera_initialization_error_can_be_retried(camera_context, error):
    context = camera_context
    context.photos.initialize_camera.side_effect = [error, None]

    async def run():
        await mount_screen(context)
        assert context.screen._status_title.value == "Camera unavailable"
        assert context.screen._status_message.value == "We couldn't start the camera. Please try again."
        assert context.screen._identify_button.disabled
        assert context.screen._status_action.visible
        await context.screen._status_action.on_click(None)
        assert not context.screen._identify_button.disabled
        assert not context.screen._status_panel.visible

    asyncio.run(run())

    assert context.photos.initialize_camera.await_count == 2
    context.on_identify.assert_not_awaited()


def test_large_photo_shows_the_warning_without_starting_identification(camera_context):
    context = camera_context
    context.photos.capture.side_effect = PhotoTooLargeError("Too large")

    async def run():
        await mount_screen(context)
        await context.screen._identify_button.on_click(None)

    asyncio.run(run())

    context.too_large.assert_awaited_once_with(context.page)
    context.on_identify.assert_not_awaited()
    context.error.assert_not_awaited()
    assert not context.screen._identify_button.disabled


@pytest.mark.parametrize("error", [OSError(), ValueError(), RuntimeError(), ft.FletException(), None])
def test_unusable_photo_is_discarded_and_can_be_retaken(camera_context, error):
    context = camera_context
    context.photos.capture.side_effect = error
    if error is None:
        context.photos.media_type = None

    async def run():
        await mount_screen(context)
        await context.screen._identify_button.on_click(None)

    asyncio.run(run())

    context.photos.discard_photo.assert_called_once_with()
    context.error.assert_awaited_once_with(
        context.page, "Could not take photo",
        "This photo couldn't be used for identification. Please take another photo.",
        action_text="Retake photo",
    )
    context.on_identify.assert_not_awaited()
    assert not context.screen._identify_button.disabled


def test_pending_initialization_blocks_retry_and_capture(camera_context):
    context = camera_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def initialize():
            started.set()
            await release.wait()

        context.photos.initialize_camera.side_effect = initialize
        context.screen.did_mount()
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            await context.screen._status_action.on_click(None)
            await context.screen._identify_button.on_click(None)
            context.photos.initialize_camera.assert_awaited_once()
            context.photos.capture.assert_not_awaited()
            assert context.screen._identify_button.disabled
        finally:
            release.set()
            await context.screen._camera_task
        assert not context.screen._identify_button.disabled

    asyncio.run(run())


def test_repeated_identify_clicks_do_not_start_another_capture(camera_context):
    context = camera_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def capture(**kwargs):
            started.set()
            await release.wait()
            return b"captured photo"

        context.photos.capture.side_effect = capture
        await mount_screen(context)
        task = asyncio.create_task(context.screen._identify_button.on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            assert context.screen._identify_button.disabled
            await context.screen._identify_button.on_click(None)
            context.photos.capture.assert_awaited_once()
        finally:
            release.set()
            await task

    asyncio.run(run())

    context.on_identify.assert_awaited_once_with(b"captured photo", "image/jpeg")


def test_unmount_cancels_camera_initialization_and_discards_the_photo(camera_context):
    context = camera_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def initialize():
            started.set()
            await release.wait()

        context.photos.initialize_camera.side_effect = initialize
        context.screen.did_mount()
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
        finally:
            context.screen.will_unmount()
            with pytest.raises(asyncio.CancelledError):
                await context.screen._camera_task
        await context.screen._identify_button.on_click(None)

    asyncio.run(run())

    context.photos.discard_photo.assert_called_once_with()
    context.photos.capture.assert_not_awaited()
    assert context.screen._identify_button.disabled


@pytest.mark.parametrize("operation", ["initialization", "capture"])
def test_late_camera_result_cannot_restart_an_unmounted_screen(camera_context, operation):
    context = camera_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def late_result(**kwargs):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return b"late photo"

        if operation == "initialization":
            context.photos.initialize_camera.side_effect = late_result
            context.screen.did_mount()
            task = context.screen._camera_task
        else:
            await mount_screen(context)
            context.photos.capture.side_effect = late_result
            task = asyncio.create_task(context.screen._identify_button.on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            context.screen.will_unmount()
        finally:
            release.set()
            await task
        assert context.screen._identify_button.disabled

    asyncio.run(run())

    context.on_identify.assert_not_awaited()
    context.error.assert_not_awaited()
    context.photos.discard_photo.assert_called_once_with()


def test_preview_updates_only_while_the_screen_is_active(camera_context):
    context = camera_context

    async def run():
        await mount_screen(context)
        context.screen._resize_preview(SimpleNamespace(width=280, height=210))
        context.photos.camera.on_state_change(SimpleNamespace(
            aspect_ratio=16 / 9, device_orientation=ft.DeviceOrientation.LANDSCAPE_LEFT,
            locked_capture_orientation=None, preview_pause_orientation=None,
        ))
        assert context.photos.camera.width / context.photos.camera.height == pytest.approx(16 / 9)
        context.photos.camera.update.reset_mock()
        context.screen.will_unmount()
        context.screen._resize_preview(SimpleNamespace(width=210, height=280))
        context.photos.camera.update.assert_not_called()

    asyncio.run(run())
