"""Show the loading message and the cancel action."""

from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.ui.components import action_button, soft_card
from medclue_mobile.ui.theme import PRIMARY_COLOR, ACCENT_COLOR, LAVENDER_SURFACE, SCREEN_MARGIN, SECTION_SPACING


class IdentifyingMedicationScreen(ft.Container):
    def __init__(self, on_cancel: Callable[[], Awaitable[None]]):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
        self._on_cancel = on_cancel
        self._cancelling = False
        self._cancel_button = action_button("Cancel", self._cancel, kind="secondary")
        self.content = ft.SafeArea(
            content=soft_card(ft.Column(
                controls=[
                    ft.Container(content=ft.Stack([
                        ft.Container(content=ft.Icon(ft.Icons.CAMERA_ALT_OUTLINED, color=PRIMARY_COLOR, size=28),
                                     width=72, height=72, bgcolor=LAVENDER_SURFACE, border_radius=36, alignment=ft.Alignment.CENTER),
                        ft.ProgressRing(width=72, height=72, color=ACCENT_COLOR, stroke_width=3),
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
                    ft.Row(controls=[self._cancel_button]),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SECTION_SPACING,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ))
        )

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
