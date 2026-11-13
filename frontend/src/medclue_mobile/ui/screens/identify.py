"""Show the live camera and start identification with one capture."""

from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.api_client import PhotoTooLargeError
from medclue_mobile.photos import CameraPermissionError, PhotoManager
from medclue_mobile.ui.components import action_button, soft_card
from medclue_mobile.ui.dialogs import show_error, show_photo_too_large
from medclue_mobile.ui.theme import (
    ACCENT_COLOR,
    CARD_COLOR,
    CARD_SPACING,
    CONTENT_PADDING,
    ICON_SIZE,
    SCREEN_MARGIN,
    SECTION_SPACING,
)


class IdentifyScreen(ft.Container):
    def __init__(
        self,
        photos: PhotoManager,
        on_identify: Callable[[bytes, str], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
        self._photos = photos
        self._on_identify = on_identify
        self._active = False
        self._ready = False
        self._busy = False
        self._camera_task = None
        self._preview_width = 0
        self._preview_height = 0
        self._preview_ratio = 3 / 4
        photos.camera.expand = False
        photos.camera.left = 0
        photos.camera.top = 0
        photos.camera.on_state_change = self._camera_changed
        self._status_title = ft.Text(
            "Starting camera...", theme_style=ft.TextThemeStyle.TITLE_LARGE,
            text_align=ft.TextAlign.CENTER,
        )
        self._status_message = ft.Text(
            "Please wait while the camera starts.", text_align=ft.TextAlign.CENTER
        )
        self._status_action = ft.TextButton("Try again", on_click=self._retry_camera, visible=False)
        self._status_panel = ft.Container(
            content=ft.Column(
                controls=[self._status_title, self._status_message, self._status_action],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=CARD_SPACING,
                scroll=ft.ScrollMode.AUTO,
            ),
            bgcolor=CARD_COLOR,
            padding=CONTENT_PADDING,
            alignment=ft.Alignment.CENTER,
        )
        guide_side = ft.BorderSide(2, ACCENT_COLOR)
        self._guide = ft.Container(
            content=ft.Stack(controls=[
                ft.Container(
                    width=ICON_SIZE, height=ICON_SIZE, top=0, left=0,
                    border=ft.Border(top=guide_side, left=guide_side),
                ),
                ft.Container(
                    width=ICON_SIZE, height=ICON_SIZE, top=0, right=0,
                    border=ft.Border(top=guide_side, right=guide_side),
                ),
                ft.Container(
                    width=ICON_SIZE, height=ICON_SIZE, bottom=0, left=0,
                    border=ft.Border(bottom=guide_side, left=guide_side),
                ),
                ft.Container(
                    width=ICON_SIZE, height=ICON_SIZE, bottom=0, right=0,
                    border=ft.Border(bottom=guide_side, right=guide_side),
                ),
            ]),
            margin=SECTION_SPACING,
            visible=False,
            ignore_interactions=True,
            border=ft.Border.all(0.5, ACCENT_COLOR),
        )
        camera_card = ft.Container(
            ft.Stack(
                controls=[photos.camera, self._guide, self._status_panel],
                fit=ft.StackFit.EXPAND,
            ),
            border_radius=16,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )
        camera_card.aspect_ratio = 4 / 3
        camera_card.on_size_change = self._resize_preview
        self._identify_button = action_button("Identify medication", self._identify, icon=ft.Icons.CAMERA_ALT_OUTLINED, rounded=False)
        self._identify_button.disabled = True
        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.Column(
                        controls=[soft_card(ft.Column(
                            controls=[camera_card, ft.Row(controls=[self._identify_button])],
                            spacing=CONTENT_PADDING, tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        ))],
                        spacing=CARD_SPACING,
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                ],
                spacing=SECTION_SPACING,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )

    def did_mount(self) -> None:
        self._active = True
        self._camera_task = self.page.run_task(self._initialize_camera)

    def will_unmount(self) -> None:
        self._active = False
        self._ready = False
        if self._camera_task is not None:
            self._camera_task.cancel()
        self._photos.discard_photo()

    def _resize_preview(self, event: ft.LayoutSizeChangeEvent) -> None:
        self._preview_width, self._preview_height = event.width, event.height
        self._fit_preview()

    def _camera_changed(self, event: ft.Event) -> None:
        ratio = event.aspect_ratio
        if ratio is None or ratio <= 0:
            return
        orientation = event.preview_pause_orientation or event.locked_capture_orientation or event.device_orientation
        landscape = orientation in (ft.DeviceOrientation.LANDSCAPE_LEFT, ft.DeviceOrientation.LANDSCAPE_RIGHT)
        self._preview_ratio = max(ratio, 1 / ratio) if landscape else min(ratio, 1 / ratio)
        self._fit_preview()

    def _fit_preview(self) -> None:
        if not self._active or self._preview_width <= 0 or self._preview_height <= 0:
            return
        camera = self._photos.camera
        camera.width = max(self._preview_width, self._preview_height * self._preview_ratio)
        camera.height = camera.width / self._preview_ratio
        camera.left = (self._preview_width - camera.width) / 2
        camera.top = (self._preview_height - camera.height) / 2
        camera.update()

    async def _initialize_camera(self) -> None:
        if not self._active or self._busy:
            return
        self._ready = False
        self._guide.visible = False
        self._status_title.value = "Starting camera..."
        self._status_message.value = "Please wait while the camera starts."
        self._status_action.visible = False
        self._status_panel.visible = True
        self._set_busy(True)
        try:
            await self._photos.initialize_camera()
            if self._active:
                self._ready = True
                self._guide.visible = True
                self._status_panel.visible = False
        except CameraPermissionError:
            self._show_camera_error(
                "Camera access is off",
                "Allow camera access in Settings to take photos.",
                permission_denied=True,
            )
        except (OSError, ValueError, RuntimeError, ft.FletException):
            self._show_camera_error("Camera unavailable", "We couldn't start the camera. Please try again.")
        finally:
            self._set_busy(False)

    def _show_camera_error(self, title: str, message: str, *, permission_denied: bool = False) -> None:
        self._ready = False
        self._guide.visible = False
        self._status_title.value = title
        self._status_message.value = message
        self._status_action.visible = not permission_denied
        self._status_panel.visible = True

    async def _retry_camera(self, event: ft.Event) -> None:
        await self._initialize_camera()

    async def _identify(self, event: ft.Event) -> None:
        if not self._active or not self._ready or self._busy:
            return
        self._set_busy(True)
        try:
            try:
                photo = await self._photos.capture(for_identification=True)
                media_type = self._photos.media_type
                if media_type is None:
                    raise ValueError("The captured photo has no media type.")
            except PhotoTooLargeError:
                if self._active:
                    await show_photo_too_large(self.page)
                return
            except CameraPermissionError:
                self._show_camera_error(
                    "Camera access is off",
                    "Allow camera access in Settings to take photos.",
                    permission_denied=True,
                )
                return
            except (OSError, ValueError, RuntimeError, ft.FletException):
                if self._active:
                    self._photos.discard_photo()
                    await show_error(
                        self.page,
                        "Could not take photo",
                        "This photo couldn't be used for identification. Please take another photo.",
                        action_text="Retake photo",
                    )
                return

            if self._active:
                await self._on_identify(photo, media_type)
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._identify_button.disabled = busy or not self._ready or not self._active
        self._status_action.disabled = busy
        if self._active and self.parent is not None:
            self.update()
