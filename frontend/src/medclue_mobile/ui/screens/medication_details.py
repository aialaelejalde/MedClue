"""Show a saved medication and its available actions."""

import sqlite3
from collections.abc import Awaitable, Callable
from copy import deepcopy

import flet as ft

from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.medications import Medication, validate_medication
from medclue_mobile.ui.components import floating_action_spacer, medication_name, medication_photo, soft_section, use_chips
from medclue_mobile.ui.dialogs import confirm_delete_medication, show_error
from medclue_mobile.ui.medication_form import (AMOUNT_UNIT_LABELS, FOOD_LABELS, FREQUENCY_LABELS, TREATMENT_END_LABELS)
from medclue_mobile.ui.theme import CARD_SPACING, SCREEN_MARGIN


class MedicationDetailsScreen(ft.Container):
    def __init__(
        self,
        cabinet: MedicationCabinet,
        medication: Medication,
        on_edit: Callable[[int], Awaitable[None]],
        on_deleted: Callable[[], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
        validate_medication(medication)
        if medication.id is None:
            raise ValueError("Medication details require a saved record.")

        self._cabinet = cabinet
        self._medication = deepcopy(medication)
        self._on_edit = on_edit
        self._on_deleted = on_deleted
        self._busy = False
        self._deleted = False
        self._edit_button = ft.FloatingActionButton(
            icon=ft.Icons.EDIT,
            tooltip="Edit medication",
            shape=ft.CircleBorder(),
            on_click=self._edit,
        )
        self._delete_button = ft.OutlinedButton("Delete medication", on_click=self._delete)
        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.ListView(
                        controls=[
                            *self._saved_information(), self._delete_button,
                            floating_action_spacer(self._edit_button, spacing=CARD_SPACING),
                        ],
                        spacing=CARD_SPACING,
                        expand=True,
                    ),
                ],
                spacing=CARD_SPACING,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )

    def _saved_information(self) -> list[ft.Control]:
        medication = self._medication
        controls = [
            medication_name(medication.name, theme_style=ft.TextThemeStyle.HEADLINE_LARGE),
            medication_photo(medication.photo, height=180, aspect_ratio=4 / 3, fit=ft.BoxFit.COVER),
        ]
        if medication.uses:
            controls.append(soft_section("Prescribed for", [use_chips(medication.uses, full_text=True)]))

        if medication.amount is not None:
            amount = medication.amount
            text = amount.text
            if amount.type == "quantity":
                quantity = str(amount.value).removesuffix(".0")
                text = f"{quantity} {AMOUNT_UNIT_LABELS[amount.unit]}"
            controls.append(soft_section("Amount to take", [ft.Text(text)]))

        if medication.frequency is not None:
            frequency = medication.frequency
            if frequency.type == "interval":
                interval = str(frequency.value).removesuffix(".0")
                unit = frequency.unit.removesuffix("s") if frequency.value == 1 else frequency.unit
                text = f"Every {interval} {unit}"
            elif frequency.type == "custom":
                text = frequency.text
            else:
                text = FREQUENCY_LABELS[frequency.type]
            controls.append(soft_section("Frequency", [ft.Text(text)]))

        if medication.food is not None:
            food = medication.food
            text = food.text if food.type == "custom" else FOOD_LABELS[food.type]
            controls.append(soft_section("Food instructions", [ft.Text(text)]))

        if medication.prescription_date is not None:
            controls.append(soft_section("Prescription date", [ft.Text(medication.prescription_date.isoformat())]))

        if medication.treatment_end is not None:
            treatment_end = medication.treatment_end
            text = (
                treatment_end.end_date.isoformat()
                if treatment_end.type == "date" else TREATMENT_END_LABELS[treatment_end.type]
            )
            controls.append(soft_section("End of treatment", [ft.Text(text)]))

        if medication.notes and medication.notes.strip():
            controls.append(soft_section("Additional notes", [ft.Text(medication.notes)]))
        return controls

    async def _edit(self, event: ft.Event) -> None:
        if self._busy or self._deleted:
            return
        self._set_busy(True)
        try:
            await self._on_edit(self._medication.id)
        finally:
            self._set_busy(False)

    async def _delete(self, event: ft.Event) -> None:
        if self._busy or self._deleted:
            return
        self._set_busy(True)
        try:
            if not await confirm_delete_medication(self.page):
                return
            while True:
                try:
                    self._cabinet.delete_medication(self._medication.id)
                    break
                except (sqlite3.Error, OSError, ValueError, LookupError):
                    retry = await show_error(
                        self.page,
                        "Cannot delete medication",
                        "We couldn't delete this medication. Please try again.",
                        action_text="Try again",
                    )
                    if not retry:
                        return

            self._deleted = True
            await self._on_deleted()
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._edit_button.disabled = busy or self._deleted
        self._delete_button.disabled = busy or self._deleted
        if self.parent is not None:
            self.update()
