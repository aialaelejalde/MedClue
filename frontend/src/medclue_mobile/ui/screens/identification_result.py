"""Show the confirmed medication and any available official uses."""

from collections.abc import Awaitable, Callable
from copy import deepcopy

import flet as ft

from medclue_mobile.medications import Medication, validate_medication
from medclue_mobile.ui.components import medication_name, medication_photo, soft_section, use_chips
from medclue_mobile.ui.theme import CARD_SPACING, SCREEN_MARGIN, SECTION_SPACING


class IdentificationResultScreen(ft.Container):
    def __init__(
        self,
        result: dict,
        photo: bytes | None,
        on_save: Callable[[Medication, list[str]], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
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

        self._medication = Medication(name=name.strip(), photo=photo)
        validate_medication(self._medication)
        self._official_uses = list(official_uses)
        self._on_save = on_save
        self._opening_form = False
        self._save_button = ft.FilledButton(
            "Save to My medications", on_click=self._save, expand=True
        )

        controls = [
            medication_photo(photo, height=180, aspect_ratio=4 / 3, fit=ft.BoxFit.COVER),
            medication_name(name, theme_style=ft.TextThemeStyle.HEADLINE_LARGE),
        ]
        if self._official_uses:
            controls.append(soft_section("What is it used for?", [use_chips(self._official_uses, full_text=True)]))

        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.ListView(controls=controls, spacing=SECTION_SPACING, expand=True),
                    ft.Row(controls=[self._save_button]),
                ],
                spacing=CARD_SPACING,
                expand=True,
            )
        )

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
        if self.parent is not None:
            self.update()
