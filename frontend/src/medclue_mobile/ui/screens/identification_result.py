"""Show the confirmed medication and any available official uses."""

from collections.abc import Awaitable, Callable
from copy import deepcopy

import flet as ft

from medclue_mobile.medications import Medication, validate_medication
from medclue_mobile.ui.components import action_button, medication_name, medication_subtitle, result_layout, status_photo, use_chips
from medclue_mobile.ui.theme import SCREEN_MARGIN, SECTION_SPACING


class IdentificationResultScreen(ft.Container):
    def __init__(
        self,
        result: dict,
        photo: bytes | None,
        on_save: Callable[[Medication, list[str]], Awaitable[None]],
        on_identify: Callable[[], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=ft.Padding.symmetric(horizontal=SCREEN_MARGIN))
        if not isinstance(result, dict) or result.get("status") != "verified":
            raise ValueError("A confirmed identification result is required.")
        medication = result.get("medication")
        if not isinstance(medication, dict):
            raise ValueError("A confirmed medication is required.")
        name = medication.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("The confirmed medication name must contain text.")
        official_uses = result.get("official_uses", [])
        if not isinstance(official_uses, list) or any(
            not isinstance(use, str) or not use.strip() for use in official_uses
        ):
            raise ValueError("Official uses must be a list of nonempty labels.")

        self._medication = Medication(name=name.strip(), photo=photo, strength=medication.get("strength"), form=medication.get("form"))
        validate_medication(self._medication)
        self._official_uses = list(official_uses)
        self._on_save = on_save
        self._on_identify = on_identify
        self._opening_form = False
        self._save_button = action_button("Save to my medications", self._save, icon=ft.Icons.ADD_CIRCLE_OUTLINE)
        self._identify_button = action_button("Identify another medication", self._identify, icon=ft.Icons.CAMERA_ALT_OUTLINED, kind="secondary")

        controls = [
            status_photo(photo, "verified", "Identified"),
            medication_name(name, theme_style=ft.TextThemeStyle.TITLE_LARGE),
            medication_subtitle(self._medication.strength, self._medication.form),
        ]
        if self._official_uses:
            controls.extend([ft.Text("What is it used for?", theme_style=ft.TextThemeStyle.TITLE_MEDIUM), use_chips(self._official_uses, full_text=True)])

        self.content = result_layout(controls, [self._save_button, self._identify_button],
                                     action_spacing=SECTION_SPACING)

    async def _identify(self, event: ft.Event) -> None:
        if self._opening_form:
            return
        self._set_opening_form(True)
        try:
            await self._on_identify()
        finally:
            self._set_opening_form(False)

    async def _save(self, event: ft.Event) -> None:
        """Open the Add medication form with the identified medication data."""
        if self._opening_form:
            return
        self._set_opening_form(True)
        try:
            await self._on_save(deepcopy(self._medication), list(self._official_uses))
        finally:
            self._set_opening_form(False)

    def _set_opening_form(self, opening: bool) -> None:
        self._opening_form = opening
        self._save_button.disabled = opening
        self._identify_button.disabled = opening
        if self.parent is not None:
            self.update()
