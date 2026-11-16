"""Show the identification loading message and the cancel action."""

from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.ui.components import action_button, result_layout
from medclue_mobile.ui.theme import ACCENT_COLOR, LAVENDER_SURFACE, PRIMARY_COLOR, SCREEN_MARGIN


LOADING_INDICATOR_SIZE = 72
LOADING_ICON_SIZE = 28
LOADING_RING_STROKE_WIDTH = 3


class IdentifyingMedicationScreen(ft.Container):
    def __init__(self, on_cancel: Callable[[], Awaitable[None]]):
        super().__init__(expand=True, padding=ft.Padding.symmetric(horizontal=SCREEN_MARGIN))
        self._on_cancel = on_cancel
        self._cancelling = False
        self._cancel_button = action_button("Cancel", self._cancel, kind="tertiary")
        self.content = result_layout([
            ft.Container(content=ft.Stack([
                ft.Container(
                    content=ft.Icon(ft.Icons.CAMERA_ALT_OUTLINED, color=PRIMARY_COLOR, size=LOADING_ICON_SIZE),
                    width=LOADING_INDICATOR_SIZE, height=LOADING_INDICATOR_SIZE,
                    bgcolor=LAVENDER_SURFACE, border_radius=LOADING_INDICATOR_SIZE / 2,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.ProgressRing(
                    width=LOADING_INDICATOR_SIZE, height=LOADING_INDICATOR_SIZE,
                    color=ACCENT_COLOR, stroke_width=LOADING_RING_STROKE_WIDTH,
                ),
            ]), alignment=ft.Alignment.CENTER),
            ft.Text(
                "Identifying medication...",
                theme_style=ft.TextThemeStyle.TITLE_LARGE,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Text(
                "Please wait while we identify your medication.",
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                text_align=ft.TextAlign.CENTER,
            ),
        ], [self._cancel_button], center_information=True)

    async def _cancel(self, event: ft.Event) -> None:
        if self._cancelling:
            return
        self._set_cancelling(True)
        try:
            await self._on_cancel()
        finally:
            self._set_cancelling(False)

    def _set_cancelling(self, cancelling: bool) -> None:
        self._cancelling = cancelling
        self._cancel_button.disabled = cancelling
        if self.parent is not None:
            self.update()
