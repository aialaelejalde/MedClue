"""Show the loading message and the cancel action."""

from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.ui.theme import PRIMARY_COLOR, SCREEN_MARGIN, SECTION_SPACING


class IdentifyingMedicationScreen(ft.Container):
    def __init__(self, on_cancel: Callable[[], Awaitable[None]]):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
        self._on_cancel = on_cancel
        self._cancelling = False
        self._cancel_button = ft.TextButton("Cancel", on_click=self._cancel)
        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.ProgressRing(color=PRIMARY_COLOR),
                    ft.Text(
                        "Identifying medication...",
                        theme_style=ft.TextThemeStyle.HEADLINE_LARGE,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "Please wait while we identify your medication.",
                        theme_style=ft.TextThemeStyle.BODY_LARGE,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    self._cancel_button,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SECTION_SPACING,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
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
