"""Show a saved medication and its available actions."""

from collections.abc import Awaitable, Callable
from copy import deepcopy

import flet as ft

from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.medications import Medication, validate_medication
from medclue_mobile.ui.components import DeviceDate, action_button, information_row, medication_name, medication_photo, medication_subtitle, soft_section, use_chips
from medclue_mobile.ui.dialogs import delete_medication_with_confirmation
from medclue_mobile.ui.medication_form import (AMOUNT_UNIT_LABELS, FOOD_LABELS, FREQUENCY_LABELS, TREATMENT_END_LABELS)
from medclue_mobile.ui.theme import BACKGROUND_COLOR, CARD_SPACING, CONTENT_PADDING, SCREEN_MARGIN, TEXT_COLOR


class MedicationDetailsScreen(ft.Container):
    def __init__(
        self,
        cabinet: MedicationCabinet,
        medication: Medication,
        on_edit: Callable[[int], Awaitable[None]],
        on_deleted: Callable[[], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=ft.Padding.symmetric(horizontal=SCREEN_MARGIN))
        validate_medication(medication)
        if medication.id is None:
            raise ValueError("Medication details require a saved record.")

        self._cabinet = cabinet
        self._medication = deepcopy(medication)
        self._on_edit = on_edit
        self._on_deleted = on_deleted
        self._busy = False
        self._deleted = False
        self._edit_button = action_button("Edit medication", self._edit, icon=ft.Icons.EDIT_OUTLINED)
        self._delete_button = action_button("Delete medication", self._delete, icon=ft.Icons.DELETE_OUTLINE, kind="danger")
        self.content = ft.SafeArea(avoid_intrusions_top=False, avoid_intrusions_bottom=False,
            content=ft.Column(
                controls=[
                    ft.ListView(
                        controls=[
                            *self._saved_information(), ft.Row([self._edit_button]), ft.Row([self._delete_button]),
                        ],
                        spacing=CARD_SPACING,
                        expand=True,
                        padding=ft.Padding.symmetric(vertical=SCREEN_MARGIN),
                    ),
                ],
                spacing=CARD_SPACING,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )

    def _saved_information(self) -> list[ft.Control]:
        medication = self._medication
        controls = [soft_section("Medication", [
            medication_photo(medication.photo, height=180, aspect_ratio=4 / 3, fit=ft.BoxFit.COVER),
            medication_name(medication.name, theme_style=ft.TextThemeStyle.TITLE_LARGE),
            medication_subtitle(medication.strength, medication.form),
        ])]
        if medication.uses:
            controls.append(soft_section("Prescribed for", [use_chips(medication.uses, full_text=True)]))

        instructions = []
        if medication.amount is not None:
            amount = medication.amount
            text = amount.text
            if amount.type == "quantity":
                quantity = str(amount.value).removesuffix(".0")
                text = f"{quantity} {AMOUNT_UNIT_LABELS[amount.unit]}"
            instructions.append(information_row("Amount", text))

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
            instructions.append(information_row("Frequency", text))

        if medication.food is not None:
            food = medication.food
            text = food.text if food.type == "custom" else FOOD_LABELS[food.type]
            instructions.append(information_row("Meal intake", text))

        if instructions:
            controls.append(soft_section("My instructions", instructions))

        dates = []
        if medication.prescription_date is not None:
            dates.append(information_row("Prescribed on", DeviceDate(medication.prescription_date)))

        if medication.treatment_end is not None:
            treatment_end = medication.treatment_end
            text = (
                DeviceDate(treatment_end.end_date)
                if treatment_end.type == "date" else TREATMENT_END_LABELS[treatment_end.type]
            )
            dates.append(information_row("End date", text))

        if medication.notes and medication.notes.strip():
            dates.extend([
                ft.Text("Notes", theme_style=ft.TextThemeStyle.BODY_MEDIUM),
                ft.Container(content=ft.Text(medication.notes, color=TEXT_COLOR), bgcolor=BACKGROUND_COLOR, padding=CONTENT_PADDING, border_radius=12),
            ])
        if dates:
            controls.append(soft_section("Dates & notes", dates))
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
            if not await delete_medication_with_confirmation(
                self.page, lambda: self._cabinet.delete_medication(self._medication.id),
            ):
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
