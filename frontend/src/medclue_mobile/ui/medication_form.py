"""Build the form for adding and editing a medication."""

from copy import deepcopy
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime

import flet as ft

from medclue_mobile.medications import (
    AMOUNT_UNITS,
    FREQUENCY_UNITS,
    Amount,
    FoodInstructions,
    Frequency,
    Medication,
    TreatmentEnd,
    validate_medication,
)
from medclue_mobile.ui.components import medication_photo, soft_section
from medclue_mobile.ui.theme import (
    ACCENT_COLOR, BLUE_SURFACE, CARD_COLOR, PRIMARY_COLOR, TEXT_COLOR,
    CARD_SPACING, CONTENT_PADDING, INPUT_RADIUS, MIN_TOUCH_TARGET_SIZE, SECTION_SPACING,
)


FREQUENCY_LABELS = {
    "once_daily": "Once a day",
    "twice_daily": "Twice a day",
    "three_times_daily": "Three times a day",
    "interval": "Every X",
    "as_needed": "As needed",
    "custom": "Other / Custom instructions",
    "not_specified": "Not specified",
}
FOOD_LABELS = {
    "before_meals": "Before meals",
    "with_food": "With food",
    "after_meals": "After meals",
    "empty_stomach": "On an empty stomach",
    "with_or_without_food": "With or without food",
    "not_applicable": "Not applicable",
    "custom": "Other / Custom instructions",
}
TREATMENT_END_LABELS = {
    "date": "I have an end date",
    "no_end_date": "No end date was given",
    "not_taking": "I'm not currently taking it",
    "unknown": "I don't know",
}
AMOUNT_UNIT_LABELS = {
    "tablets": "Tablet(s)", "capsules": "Capsule(s)", "mL": "mL",
    "drops": "Drop(s)", "puffs": "Puff(s)", "sprays": "Spray(s)",
    "sachets": "Sachet(s)", "patches": "Patch(es)", "mg": "mg", "g": "g",
}
UNKNOWN_REASON = "I don't know / I don't remember"


class _UseOption(ft.Container):
    """An accessible text option whose selected state is shown in blue."""

    def __init__(self, label: str, value: bool, on_change: Callable[[ft.Event], None]):
        super().__init__(
            content=ft.Semantics(content=ft.Text(label, size=14), button=True, selected=value),
            padding=CONTENT_PADDING, border_radius=INPUT_RADIUS, ink=True, on_click=self._toggle,
        )
        self._on_change = on_change
        self.value = value

    @property
    def value(self) -> bool:
        return self._value

    @value.setter
    def value(self, selected: bool) -> None:
        self._value = selected
        self.bgcolor = BLUE_SURFACE if selected else CARD_COLOR
        self.content.selected = selected
        self.content.content.color = PRIMARY_COLOR if selected else TEXT_COLOR

    def _toggle(self, event: ft.Event) -> None:
        self.value = not self.value
        self._on_change(event)


class MedicationForm(ft.Column):
    def __init__(
        self,
        medication: Medication | None = None,
        *,
        official_uses: list[str] | None = None,
        suggested_name: bool = False,
        on_take_photo: ft.ControlEventHandler[ft.TextButton] | None = None,
    ):
        super().__init__(
            spacing=SECTION_SPACING, scroll=ft.ScrollMode.AUTO, expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._original = deepcopy(medication) if medication is not None else Medication()
        self._photo = self._original.photo
        self._prescription_date = self._original.prescription_date
        self._end_date = (self._original.treatment_end.end_date if self._original.treatment_end else None)

        self.name_field = ft.TextField(
            border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
            label="Suggested name" if suggested_name else "Medication name",
            value=self._original.name or "",
            helper=(
                ft.Text("Please check this suggested name before saving.", theme_style=ft.TextThemeStyle.BODY_SMALL)
                if suggested_name else None
            ),
        )
        self._photo_preview = medication_photo(self._photo, height=180, aspect_ratio=4 / 3, fit=ft.BoxFit.COVER)
        self._take_photo_button = ft.OutlinedButton(
            "Change photo" if self._photo else "Take photo",
            on_click=on_take_photo,
            disabled=on_take_photo is None,
            expand=True,
        )
        self._remove_photo_button = ft.OutlinedButton(
            "Remove photo", on_click=lambda event: self.set_photo(None), visible=bool(self._photo),
            expand=True,
        )

        self._official_uses = list(dict.fromkeys(official_uses or []))
        custom_reasons = [
            reason for reason in dict.fromkeys(self._original.uses)
            if reason not in self._official_uses and reason != UNKNOWN_REASON
        ]
        self._use_options = [
            _UseOption(use, use in self._original.uses, self._options_changed)
            for use in self._official_uses
        ]
        self._use_summary = ft.Text(theme_style=ft.TextThemeStyle.BODY_SMALL)
        selector_shape = ft.RoundedRectangleBorder(radius=INPUT_RADIUS, side=ft.BorderSide(1, ACCENT_COLOR))
        self._use_list = ft.ListView(controls=[ft.Column(
            controls=self._use_options,
            spacing=CARD_SPACING,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            tight=True,
            on_size_change=self._resize_use_list,
        )])
        self._use_selector = ft.ExpansionTile(
            title=ft.Text("Select the uses that apply to you", theme_style=ft.TextThemeStyle.BODY_LARGE),
            subtitle=ft.Container(content=self._use_summary, padding=ft.Padding.only(top=6)),
            controls=[self._use_list],
            controls_padding=ft.Padding.only(left=CONTENT_PADDING, right=CONTENT_PADDING, bottom=CARD_SPACING),
            expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
            shape=selector_shape,
            collapsed_shape=selector_shape,
            maintain_state=True,
            visible=bool(self._use_options),
        )
        self._own_reason = ft.Checkbox(
            label="Other — Add my own reason", value=bool(custom_reasons),
            visible=bool(self._use_options), on_change=self._options_changed,
        )
        self._reason_fields = [
            _reason_field(reason) for reason in (custom_reasons or [""])
        ]
        self._reason_group = ft.Column(
            controls=[*self._reason_fields, ft.TextButton("Add reason", on_click=self._add_reason)],
            spacing=CARD_SPACING, tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._unknown_reason = ft.Checkbox(label=UNKNOWN_REASON, value=UNKNOWN_REASON in self._original.uses)

        amount = self._original.amount
        self.amount_custom = ft.Checkbox(
            label="Write my own amount or instructions",
            value=amount is not None and amount.type == "custom", on_change=self._options_changed,
        )
        self.amount_value = ft.TextField(
            label="Quantity", value=_number_text(amount.value) if amount else "", expand=True,
            border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
        )
        self.amount_unit = _dropdown(
            "Unit", {unit: AMOUNT_UNIT_LABELS[unit] for unit in AMOUNT_UNITS},
            amount.unit if amount else None,
        )
        self.amount_text = ft.TextField(
            label="My amount or instructions", value=(amount.text or "") if amount else "", multiline=True,
            border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
        )
        self._quantity_group = ft.Row(controls=[self.amount_value, self.amount_unit], spacing=CARD_SPACING)

        frequency = self._original.frequency
        self.frequency_type = _dropdown("Frequency", FREQUENCY_LABELS, frequency.type if frequency else None)
        self.frequency_type.on_select = self._options_changed
        self.frequency_value = ft.TextField(
            label="Every", value=_number_text(frequency.value) if frequency else "",
            border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
        )
        self.frequency_unit = _dropdown(
            "Time unit", {unit: unit.capitalize() for unit in FREQUENCY_UNITS},
            frequency.unit if frequency else None,
        )
        self._interval_group = ft.Column(
            controls=[self.frequency_value, ft.Row(controls=[self.frequency_unit])], spacing=CARD_SPACING, tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self.frequency_text = ft.TextField(
            label="My frequency instructions", value=(frequency.text or "") if frequency else "", multiline=True,
            border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
        )

        food = self._original.food
        self.food_type = _dropdown("Food instructions", FOOD_LABELS, food.type if food else None)
        self.food_type.on_select = self._options_changed
        self.food_text = ft.TextField(
            label="My food instructions", value=(food.text or "") if food else "", multiline=True,
            border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
        )

        self._prescription_button = ft.OutlinedButton(on_click=lambda event: self._pick_date(False))
        self._clear_prescription_button = ft.OutlinedButton("Clear date", on_click=lambda event: self._set_date(False, None))
        treatment_end = self._original.treatment_end
        self.treatment_end_type = _dropdown(None, TREATMENT_END_LABELS, treatment_end.type if treatment_end else None)
        self.treatment_end_type.on_select = self._options_changed
        self._end_button = ft.OutlinedButton(on_click=lambda event: self._pick_date(True))
        self._clear_end_button = ft.OutlinedButton("Clear date", on_click=lambda event: self._set_date(True, None))
        self._end_date_group = ft.Row(controls=[self._end_button, self._clear_end_button], wrap=True)
        self.notes_field = ft.TextField(
            border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
            label="Additional notes", value=self._original.notes or "", multiline=True,
            hint_text="Write anything you'd like to remember about this medication...",
            text_vertical_align=-1,
            align_label_with_hint=True,
            min_lines=3,
        )

        self.controls = [
            _form_section("Medication", [
                _field_group([
                    self._photo_preview,
                    ft.Row(
                        controls=[self._take_photo_button, self._remove_photo_button],
                        spacing=CARD_SPACING,
                    ),
                ]),
                self.name_field,
                _field_group([
                    self._use_selector, self._checkbox_row(self._own_reason),
                    self._reason_group, self._checkbox_row(self._unknown_reason),
                ], title="Prescribed for"),
            ]),
            _form_section("My instructions", [
                _field_group([
                    self._checkbox_row(self.amount_custom), self._quantity_group, self.amount_text,
                ], title="How much were you told to take or use?"),
                _field_group([
                    ft.Row(controls=[self.frequency_type]), self._interval_group, self.frequency_text,
                ], title="How often were you told to take it?"),
                _field_group([
                    ft.Row(controls=[self.food_type]), self.food_text,
                ], title="What instructions were you given about food?"),
            ]),
            _form_section("Dates & notes", [
                _field_group([
                    ft.Row(controls=[self._prescription_button, self._clear_prescription_button], wrap=True),
                ], title="Prescription date"),
                _field_group(
                    [ft.Row(controls=[self.treatment_end_type]), self._end_date_group],
                    title="End of treatment",
                ),
                self.notes_field,
            ]),
        ]
        self._fields = [
            self.name_field, *self._use_options, self._own_reason, *self._reason_fields,
            self._unknown_reason, self.amount_custom, self.amount_value, self.amount_unit,
            self.amount_text, self.frequency_type, self.frequency_value, self.frequency_unit,
            self.frequency_text, self.food_type, self.food_text, self.treatment_end_type, self.notes_field,
        ]
        self._update_visibility()
        self._update_date_labels()
        self._initial_values = self._snapshot()

    def has_changes(self) -> bool:
        """Include incomplete input so leaving cannot silently discard it."""
        return self._snapshot() != self._initial_values

    def _add_reason(self, event: ft.Event) -> None:
        field = _reason_field()
        self._reason_fields.append(field)
        self._reason_group.controls.insert(-1, field)
        self._fields.append(field)
        self._refresh()

    def _resize_use_list(self, event: ft.LayoutSizeChangeEvent) -> None:
        height = min(event.height, 240)
        if self._use_list.height != height:
            self._use_list.height = height
            if self.parent is not None:
                self._use_list.update()

    def _checkbox_row(self, checkbox: ft.Checkbox) -> ft.Container:
        """Align long checkbox labels and let them wrap within the form."""
        label = checkbox.label
        checkbox.label = None
        checkbox.semantics_label = label
        checkbox.visual_density = ft.VisualDensity.COMPACT

        def toggle(event: ft.Event) -> None:
            checkbox.value = not checkbox.value
            self._options_changed(event)

        return ft.Container(
            visible=checkbox.visible,
            content=ft.Row(
                controls=[
                    ft.Container(content=checkbox, height=MIN_TOUCH_TARGET_SIZE, alignment=ft.Alignment.CENTER, width=40),
                    ft.Text(label, expand=True),
                ], spacing=0,
            ),
            on_click=toggle,
        )

    def get_medication(self) -> Medication:
        """Return a validated draft without saving or changing the original record."""
        uses = [use for use, option in zip(self._official_uses, self._use_options) if option.value]
        if not self._use_options or self._own_reason.value:
            uses.extend(field.value for field in self._reason_fields if field.value.strip())
        if self._unknown_reason.value:
            uses.append(UNKNOWN_REASON)

        medication = replace(
            self._original,
            name=_optional_text(self.name_field.value),
            photo=self._photo,
            uses=list(dict.fromkeys(uses)),
            amount=self._get_amount(),
            frequency=self._get_frequency(),
            food=self._get_food(),
            prescription_date=self._prescription_date,
            treatment_end=self._get_treatment_end(),
            notes=_optional_text(self.notes_field.value),
        )
        validate_medication(medication)
        return medication

    def set_photo(self, photo: bytes | None) -> None:
        if photo is not None and (not isinstance(photo, bytes) or not photo):
            raise ValueError("The photo must contain image bytes.")
        self._photo = photo
        self._photo_preview.content = medication_photo(
            photo, height=180, aspect_ratio=4 / 3, fit=ft.BoxFit.COVER,
        ).content
        self._take_photo_button.content = "Change photo" if photo else "Take photo"
        self._remove_photo_button.visible = bool(photo)
        self._refresh()

    def _get_amount(self) -> Amount | None:
        if self.amount_custom.value:
            text = _optional_text(self.amount_text.value)
            return Amount("custom", text=text) if text else None
        if self.amount_value.value.strip() or self.amount_unit.value:
            return Amount(
                "quantity", value=_number(self.amount_value.value, "Quantity"),
                unit=self.amount_unit.value or None,
            )
        return None

    def _get_frequency(self) -> Frequency | None:
        frequency_type = self.frequency_type.value
        if not frequency_type:
            return None
        if frequency_type == "interval":
            return Frequency(
                frequency_type, value=_number(self.frequency_value.value, "Frequency interval"),
                unit=self.frequency_unit.value or None,
            )
        if frequency_type == "custom":
            text = _optional_text(self.frequency_text.value)
            return Frequency(frequency_type, text=text) if text else None
        return Frequency(frequency_type)

    def _get_food(self) -> FoodInstructions | None:
        food_type = self.food_type.value
        if not food_type:
            return None
        if food_type == "custom":
            text = _optional_text(self.food_text.value)
            return FoodInstructions(food_type, text=text) if text else None
        return FoodInstructions(food_type)

    def _get_treatment_end(self) -> TreatmentEnd | None:
        end_type = self.treatment_end_type.value
        if not end_type:
            return None
        return TreatmentEnd(end_type, end_date=self._end_date if end_type == "date" else None)

    def _options_changed(self, event: ft.Event) -> None:
        self._update_visibility()
        self._refresh()

    def _update_visibility(self) -> None:
        self._use_summary.value = f"{sum(bool(option.value) for option in self._use_options)} selected"
        self._reason_group.visible = not self._use_options or bool(self._own_reason.value)
        self._quantity_group.visible = not self.amount_custom.value
        self.amount_text.visible = bool(self.amount_custom.value)
        self._interval_group.visible = self.frequency_type.value == "interval"
        self.frequency_text.visible = self.frequency_type.value == "custom"
        self.food_text.visible = self.food_type.value == "custom"
        self._end_date_group.visible = self.treatment_end_type.value == "date"

    def _pick_date(self, is_end: bool) -> None:
        def select_date(event: ft.Event) -> None:
            value = event.control.value
            if isinstance(value, datetime):
                value = value.date()
            elif isinstance(value, str):
                value = date.fromisoformat(value[:10])
            self._set_date(is_end, value)

        picker = ft.DatePicker(
            value=(self._end_date if is_end else self._prescription_date) or date.today(),
            first_date=date.min,
            last_date=date.max,
            locale=ft.Locale("en", "GB"),
            help_text="End of treatment" if is_end else "Prescription date",
            cancel_text="Cancel", confirm_text="OK", on_change=select_date,
        )
        self.page.show_dialog(picker)

    def _set_date(self, is_end: bool, value: date | None) -> None:
        if is_end:
            self._end_date = value
        else:
            self._prescription_date = value
        self._update_date_labels()
        self._refresh()

    def _update_date_labels(self) -> None:
        self._prescription_button.content = (self._prescription_date.isoformat() if self._prescription_date else "Choose date")
        self._clear_prescription_button.visible = self._prescription_date is not None
        self._end_button.content = self._end_date.isoformat() if self._end_date else "Choose date"
        self._clear_end_button.visible = self._end_date is not None

    def _snapshot(self) -> tuple:
        return ([field.value for field in self._fields], self._photo, self._prescription_date, self._end_date)

    def _refresh(self) -> None:
        if self.parent is not None:
            self.update()


def form_screen_layout(title: str, form: MedicationForm, save_button: ft.FilledButton) -> ft.SafeArea:
    """Share the scrolling form and fixed save action between Add and Edit."""
    form.controls.append(ft.Container(height=MIN_TOUCH_TARGET_SIZE + CARD_SPACING))
    return ft.SafeArea(content=ft.Column(
        controls=[
            ft.Text(title, theme_style=ft.TextThemeStyle.HEADLINE_LARGE),
            ft.Stack(controls=[form, ft.Container(
                content=ft.Row([save_button]), left=0, right=0, bottom=0,
            )], fit=ft.StackFit.EXPAND, expand=True),
        ],
        spacing=CARD_SPACING, expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    ))


def _form_section(title: str, groups: list[ft.Control]) -> ft.Container:
    return soft_section(title, [ft.Column(
        controls=groups, spacing=SECTION_SPACING, tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )], spacing=CONTENT_PADDING)


def _field_group(controls: list[ft.Control], *, title: str | None = None) -> ft.Column:
    return ft.Column(
        controls=([ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM)] if title else []) + controls,
        spacing=CONTENT_PADDING, tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def _reason_field(value: str = "") -> ft.TextField:
    return ft.TextField(
        label="Reason", value=value, multiline=True,
        border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
    )


def _dropdown(label: str | None, choices: dict[str, str], value: str | None = None) -> ft.Dropdown:
    return ft.Dropdown(
        border=ft.OutlineInputBorder(border_radius=INPUT_RADIUS),
        expand=True,
        expanded_insets=ft.Padding.all(0),
        label=label,
        value=value or "",
        options=[ft.DropdownOption(key="", text="Not selected")] + [
            ft.DropdownOption(key=key, text=text) for key, text in choices.items()
        ],
    )


def _optional_text(value: str) -> str | None:
    return value if value.strip() else None


def _number_text(value: float | None) -> str:
    return str(value) if value is not None else ""


def _number(value: str, label: str) -> float:
    try:
        return float(value.strip().replace(",", "."))
    except ValueError as error:
        raise ValueError(f"{label} must contain a valid number.") from error
