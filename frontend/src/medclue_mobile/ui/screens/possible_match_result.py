"""Show an unconfirmed name and the actions allowed for its result."""

from collections.abc import Awaitable, Callable
from copy import deepcopy

import flet as ft

from medclue_mobile.medications import Medication
from medclue_mobile.ui.components import medication_name, medication_photo
from medclue_mobile.ui.theme import CARD_SPACING, SCREEN_MARGIN, SECTION_SPACING


class PossibleMatchResultScreen(ft.Container):
    def __init__(
        self,
        result: dict,
        photo: bytes | None,
        on_retry: Callable[[], Awaitable[None]],
        on_retake: Callable[[], Awaitable[None]],
        on_add: Callable[[Medication], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
        if not isinstance(result, dict) or result.get("status") not in (
            "not_identified", "no_match", "connection_error", "timeout"
        ):
            raise ValueError("An unsuccessful identification result is required.")
        status = result["status"]
        failed_step = result.get("failed_step")
        if status in ("connection_error", "timeout") and failed_step not in (
            "image_analysis", "cima_verification", "official_uses_retrieval", "uses_translation"
        ):
            raise ValueError("A failed identification must state which step failed.")
        if photo is not None and (not isinstance(photo, bytes) or not photo):
            raise ValueError("The photo must contain image bytes.")

        candidate = result.get("suggested_candidate")
        name = None
        if candidate is not None:
            if not isinstance(candidate, dict):
                raise ValueError("The suggested candidate must contain medication data.")
            name = candidate.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("The suggested medication name must contain text.")
            if status == "not_identified" or failed_step == "image_analysis":
                raise ValueError("Unfinished image analysis cannot include a suggested name.")
        if status == "no_match" and name is None:
            raise ValueError("An unconfirmed match needs a suggested medication name.")

        self._medication = Medication(name=name, photo=photo)
        self._on_retry = on_retry
        self._on_retake = on_retake
        self._on_add = on_add
        self._busy = False
        self._retry_button = ft.FilledButton(
            "Try again", on_click=self._retry, visible=status in ("connection_error", "timeout")
        )
        self._retake_button = ft.OutlinedButton(
            "Retake photo", on_click=self._retake, visible=status != "connection_error"
        )
        self._add_button = ft.TextButton("Add medication manually", on_click=self._add)

        if status == "not_identified":
            title = "Medication not identified"
            message = "We couldn't identify the medication in this photo."
        elif status == "no_match":
            title = "Possible match"
            message = (
                "This might be your medication, but we couldn't confirm it. "
                "We can't show its official uses."
            )
        elif status == "timeout":
            title = "Identification taking too long"
            message = "We couldn't finish identifying the medication in time. Please try again."
        else:
            title = "Connection problem"
            message = (
                "We couldn't identify the medication because of a connection problem. Please try again."
                if failed_step == "image_analysis" else
                "We couldn't confirm this medication because of a connection problem. "
                "Its official uses aren't available right now."
            )

        controls = [
            medication_photo(photo, height=240),
            ft.Text(title, theme_style=ft.TextThemeStyle.HEADLINE_LARGE),
        ]
        if name is not None:
            if status != "no_match":
                controls.append(ft.Text("Possible match", theme_style=ft.TextThemeStyle.TITLE_LARGE))
            controls.append(medication_name(name))
        controls.append(ft.Text(message, theme_style=ft.TextThemeStyle.BODY_LARGE))
        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.ListView(controls=controls, spacing=SECTION_SPACING, expand=True),
                    ft.Row(
                        controls=[self._retry_button, self._retake_button, self._add_button],
                        wrap=True,
                    ),
                ],
                spacing=CARD_SPACING,
                expand=True,
            )
        )

    async def _retry(self, event: ft.Event) -> None:
        if self._busy or not self._retry_button.visible:
            return
        self._set_busy(True)
        try:
            await self._on_retry()
        finally:
            self._set_busy(False)

    async def _retake(self, event: ft.Event) -> None:
        if self._busy or not self._retake_button.visible:
            return
        self._set_busy(True)
        try:
            await self._on_retake()
        finally:
            self._set_busy(False)

    async def _add(self, event: ft.Event) -> None:
        if self._busy:
            return
        self._set_busy(True)
        try:
            await self._on_add(deepcopy(self._medication))
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._retry_button.disabled = busy
        self._retake_button.disabled = busy
        self._add_button.disabled = busy
        if self.parent is not None:
            self.update()
