"""Capture a temporary photo in a camera dialog."""

import asyncio

import flet as ft

from medclue_mobile.photos import CameraPermissionError, PhotoManager
from medclue_mobile.ui.camera_preview import DEFAULT_PREVIEW_ASPECT_RATIO, fit_camera_preview, preview_aspect_ratio
from medclue_mobile.ui.components import action_button, camera_guide
from medclue_mobile.ui.dialogs import show_error
from medclue_mobile.ui.theme import (
    CAMERA_FRAME_RADIUS,
    CARD_COLOR,
    CARD_RADIUS,
    CONTENT_PADDING,
    PHOTO_FRAME_ASPECT_RATIO,
    SCREEN_MARGIN,
)


DEFAULT_PAGE_WIDTH = 360


class PhotoCaptureDialog:
    """Manage one photo capture, its result, and cleanup when the dialog ends."""

    def __init__(self, page: ft.Page):
        self._page = page
        self._photos = PhotoManager()
        self._result: asyncio.Future[bytes | None] = asyncio.get_running_loop().create_future()
        self._capturing = False
        self._closed = False
        self._preview_width = 0
        self._preview_height = 0
        self._preview_ratio = DEFAULT_PREVIEW_ASPECT_RATIO
        self._photos.camera.expand = False
        self._photos.camera.left = 0
        self._photos.camera.top = 0
        self._photos.camera.on_state_change = self._camera_changed
        self._take_button = action_button("Take photo", self._capture, icon=ft.Icons.CAMERA_ALT_OUTLINED)
        self._take_button.disabled = True
        camera_frame = ft.Container(
            content=ft.Stack(controls=[self._photos.camera, camera_guide()], fit=ft.StackFit.EXPAND),
            aspect_ratio=PHOTO_FRAME_ASPECT_RATIO,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            border_radius=CAMERA_FRAME_RADIUS,
            on_size_change=self._resize_preview,
        )
        self._dialog = ft.AlertDialog(
            content=ft.Container(
                width=max(0, (page.width or DEFAULT_PAGE_WIDTH) - 2 * (SCREEN_MARGIN + CONTENT_PADDING)),
                content=ft.Column(
                    controls=[
                        camera_frame,
                        ft.Row(controls=[self._take_button]),
                        ft.Row(controls=[action_button("Cancel", self._cancel, kind="tertiary")]),
                    ],
                    spacing=CONTENT_PADDING,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
            on_dismiss=self._dismiss,
            scrollable=True,
            bgcolor=CARD_COLOR,
            shape=ft.RoundedRectangleBorder(radius=CARD_RADIUS),
            inset_padding=ft.Padding.symmetric(horizontal=SCREEN_MARGIN, vertical=SCREEN_MARGIN),
            content_padding=ft.Padding.all(CONTENT_PADDING),
            actions_padding=0,
        )

    async def open(self) -> bytes | None:
        """Show the camera and return the captured photo or None."""
        self._page.show_dialog(self._dialog)
        try:
            try:
                await self._photos.initialize_camera()
            except CameraPermissionError:
                if self._result.done():
                    return None
                raise
            except (OSError, ValueError, RuntimeError, ft.FletException):
                if self._result.done():
                    return None
                if not self._closed:
                    await show_error(self._page, "Could not take photo", "We couldn't start the camera. Please try again.")
                return None
            if not self._result.done() and not self._closed:
                self._take_button.disabled = False
                self._dialog.update()
            return await self._result
        finally:
            self._photos.discard_photo()
            if self._dialog.open and not self._closed:
                self._page.pop_dialog()

    def close(self) -> None:
        self._closed = True
        self._dismiss()

    def _dismiss(self, event: ft.Event | None = None) -> None:
        if not self._result.done():
            self._result.set_result(None)

    def _cancel(self, event: ft.Event) -> None:
        self._dismiss()
        if self._dialog.open:
            self._page.pop_dialog()

    async def _capture(self, event: ft.Event) -> None:
        if self._capturing or self._result.done():
            return
        self._capturing = True
        self._take_button.disabled = True
        self._dialog.update()
        try:
            photo = await self._photos.capture()
            if not self._result.done():
                self._result.set_result(photo)
                self._page.pop_dialog()
        except (OSError, ValueError, RuntimeError, ft.FletException):
            if not self._result.done() and not self._closed:
                await show_error(self._page, "Could not take photo", "Please try again.")
        finally:
            self._capturing = False
            self._take_button.disabled = False
            if self._dialog.open and not self._closed:
                self._dialog.update()

    def _resize_preview(self, event: ft.LayoutSizeChangeEvent) -> None:
        self._preview_width, self._preview_height = event.width, event.height
        self._fit_preview()

    def _camera_changed(self, event: ft.Event) -> None:
        ratio = preview_aspect_ratio(event)
        if ratio is None:
            return
        self._preview_ratio = ratio
        self._fit_preview()

    def _fit_preview(self) -> None:
        if self._result.done() or self._closed:
            return
        fit_camera_preview(self._photos.camera, self._preview_width, self._preview_height, self._preview_ratio)
