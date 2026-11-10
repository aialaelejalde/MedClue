"""Show the live camera and start identification with one capture."""

from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.api_client import PhotoTooLargeError
from medclue_mobile.photos import CameraPermissionError, PhotoManager
from medclue_mobile.ui.components import soft_card
from medclue_mobile.ui.dialogs import show_error, show_photo_too_large
from medclue_mobile.ui.theme import (
    ACCENT_COLOR,
    CARD_COLOR,
    CARD_RADIUS,
    CARD_SPACING,
    CONTENT_PADDING,
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
        self._guide = ft.Container(
            margin=SECTION_SPACING,
            border=ft.Border.all(2, ACCENT_COLOR),
            border_radius=CARD_RADIUS,
            visible=False,
        )
        camera_card = soft_card(
            ft.Stack(
                controls=[photos.camera, self._guide, self._status_panel],
                fit=ft.StackFit.EXPAND,
            ),
            padding=0,
        )
        camera_card.expand = True
        self._identify_button = ft.FilledButton(
            "Identify medication", on_click=self._identify, disabled=True, expand=True
        )
        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.Text("Identify medication", theme_style=ft.TextThemeStyle.HEADLINE_LARGE),
                    camera_card,
                    ft.Row(controls=[self._identify_button]),
                ],
                spacing=SECTION_SPACING,
                expand=True,
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
