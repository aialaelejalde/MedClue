"""Test conversion of form input, selected uses, dates, and unsaved changes."""

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest

from medclue_mobile.medications import Amount, FoodInstructions, Frequency, Medication, TreatmentEnd
from medclue_mobile.ui.medication_form import MedicationForm
from medclue_mobile.ui.medication_labels import UNKNOWN_REASON


@pytest.fixture
def form():
    return MedicationForm(Medication(name="Medication"))


def test_existing_medication_is_restored_without_unsaved_changes():
    medication = Medication(
        id=7, created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        name="Medication", photo=b"photo", strength="500 mg", form="tablet",
        uses=["Personal reason", UNKNOWN_REASON], amount=Amount("quantity", 0.5, "tablets"),
        frequency=Frequency("interval", 8, "hours"), food=FoodInstructions("with_food"),
        prescription_date=date(2026, 11, 1), treatment_end=TreatmentEnd("date", date(2026, 12, 1)),
        notes="Saved notes",
    )
    restored = MedicationForm(medication)

    assert restored.get_medication() == medication
    assert not restored.has_changes()


def test_new_medication_does_not_select_official_uses_automatically():
    form = MedicationForm(Medication(name="Confirmed"), official_uses=["First use", "Second use"])

    assert form.get_medication().uses == []
    assert not form.has_changes()


def test_selecting_and_deselecting_uses_keeps_the_full_official_text():
    uses = ["A long official indication (with restrictions and conditions). " * 8, "Another use", "Unselected use"]
    form = MedicationForm(Medication(name="Confirmed"), official_uses=uses)

    form._use_options[0].on_click(None)
    form._use_options[1].on_click(None)
    assert form.get_medication().uses == uses[:2]

    form._use_options[0].on_click(None)
    assert form.get_medication().uses == [uses[1]]


def test_personal_reasons_are_included_with_official_uses_only_when_selected():
    form = MedicationForm(Medication(name="Medication"), official_uses=["Official use"])
    form._use_options[0].on_click(None)
    form._reason_fields[0].value = "My own reason"
    assert form.get_medication().uses == ["Official use"]

    form._own_reason.value = True
    form._own_reason.on_change(None)
    assert form.get_medication().uses == ["Official use", "My own reason"]

    form._own_reason.value = False
    form._own_reason.on_change(None)
    assert form.get_medication().uses == ["Official use"]


def test_selected_uses_and_personal_reasons_are_restored_when_editing():
    medication = Medication(id=7, name="Medication", uses=["Selected use", "My own reason"])
    form = MedicationForm(medication, official_uses=["Selected use", "Unselected use"])

    assert form.get_medication() == medication
    assert not form.has_changes()


def test_unknown_reason_is_saved_only_when_selected(form):
    form._unknown_reason.value = True
    assert form.get_medication().uses == [UNKNOWN_REASON]

    form._unknown_reason.value = False
    assert form.get_medication().uses == []


def test_tapping_the_unknown_reason_row_toggles_the_saved_selection(form):
    def descendants(control):
        yield control
        content = getattr(control, "content", None)
        if isinstance(content, ft.Control):
            yield from descendants(content)
        for child in getattr(control, "controls", []):
            yield from descendants(child)

    row = next(
        control for control in descendants(form)
        if isinstance(control, ft.Container) and control.on_click is not None
        and isinstance(control.content, ft.Row)
        and any(getattr(child, "content", None) is form._unknown_reason for child in control.content.controls)
    )
    row.on_click(None)
    assert form.get_medication().uses == [UNKNOWN_REASON]
    assert form.has_changes()

    row.on_click(None)
    assert form.get_medication().uses == []
    assert not form.has_changes()


def test_official_use_list_limits_its_height_without_losing_selections():
    form = MedicationForm(Medication(name="Medication"), official_uses=["First use", "Second use"])
    form._use_options[0].on_click(None)
    resize = form._use_list.controls[0].on_size_change

    resize(SimpleNamespace(height=96))
    assert form._use_list.height == 96
    resize(SimpleNamespace(height=600))
    assert 96 < form._use_list.height < 600
    resize(SimpleNamespace(height=96))
    assert form._use_list.height == 96
    assert form.get_medication().uses == ["First use"]


def test_personal_reason_can_be_added_and_removed_without_changing_the_original_reasons():
    form = MedicationForm(Medication(name="Medication", uses=["Original reason"]))
    form._reason_group.controls[-1].controls[0].on_click(None)
    added = form._reason_fields[-1]
    added.value = "New reason"
    assert form.get_medication().uses == ["Original reason", "New reason"]
    assert form.has_changes()

    added.suffix_icon.on_click(None)
    assert form.get_medication().uses == ["Original reason"]
    assert not form.has_changes()


@pytest.mark.parametrize("text,expected", [("2", 2), ("1.5", 1.5), (" 1,5 ", 1.5)])
def test_quantity_input_is_converted_to_a_number(form, text, expected):
    form.amount_value.value = text
    form.amount_unit.value = "mL"

    assert form.get_medication().amount == Amount("quantity", expected, "mL")


def test_interval_input_is_converted_with_its_unit(form):
    form.frequency_type.value = "interval"
    form.frequency_value.value = "1,5"
    form.frequency_unit.value = "hours"

    assert form.get_medication().frequency == Frequency("interval", 1.5, "hours")


def test_custom_amount_ignores_the_previous_quantity_input(form):
    form.amount_value.value = "unfinished number"
    form.amount_unit.value = "tablets"
    form.amount_custom.value = True
    form.amount_custom.on_change(None)
    form.amount_text.value = "Use as instructed"

    assert form.get_medication().amount == Amount("custom", text="Use as instructed")


@pytest.mark.parametrize("field,selector,stale_field,selection,expected", [
    ("frequency", "frequency_type", "frequency_value", "once_daily", Frequency("once_daily")),
    ("food", "food_type", "food_text", "with_food", FoodInstructions("with_food")),
])
def test_fixed_instruction_choices_ignore_input_from_other_options(form, field, selector, stale_field, selection, expected):
    getattr(form, stale_field).value = "Previous input"
    control = getattr(form, selector)
    control.value = selection
    control.on_select(None)

    assert getattr(form.get_medication(), field) == expected


@pytest.mark.parametrize("field,instruction", [
    ("frequency", Frequency("custom", text="  At bedtime  ")),
    ("food", FoodInstructions("custom", text="  After breakfast  ")),
])
def test_custom_instructions_preserve_the_entered_text_and_ignore_blank_input(form, field, instruction):
    selector = getattr(form, f"{field}_type")
    selector.value = "custom"
    selector.on_select(None)
    text = getattr(form, f"{field}_text")
    assert text.visible
    text.value = instruction.text

    assert getattr(form.get_medication(), field) == instruction

    text.value = " \t\n "
    assert getattr(form.get_medication(), field) is None


def test_mounting_loads_the_device_date_format_without_changing_saved_dates(monkeypatch):
    async def run():
        page = SimpleNamespace(
            get_device_info=AsyncMock(return_value=SimpleNamespace(locales=[ft.Locale("en", "US")])),
            run_task=lambda function: asyncio.create_task(function()),
            show_dialog=Mock(),
        )
        monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
        medication = Medication(
            name="Medication", prescription_date=date(2026, 11, 15),
            treatment_end=TreatmentEnd("date", date(2026, 12, 1)),
        )
        form = MedicationForm(medication)
        form.update = Mock()
        form.did_mount()
        await asyncio.wait_for(form._locale_task, timeout=5)

        assert form._prescription_button.content == "11/15/26"
        assert form._end_button.content == "12/1/26"
        form._prescription_button.on_click(None)
        assert page.show_dialog.call_args.args[0].locale == ft.Locale("en", "US")
        assert form.get_medication() == medication
        assert not form.has_changes()
        form.update.assert_called_once_with()

    asyncio.run(run())


def test_unmounting_cancels_a_pending_form_locale_lookup(monkeypatch, form):
    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def get_device_info():
            started.set()
            await release.wait()

        page = SimpleNamespace(
            get_device_info=AsyncMock(side_effect=get_device_info),
            run_task=lambda function: asyncio.create_task(function()),
        )
        monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
        form.update = Mock()
        form.did_mount()
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
        finally:
            form.will_unmount()
            with pytest.raises(asyncio.CancelledError):
                await form._locale_task
        form.update.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("field", ["prescription", "treatment_end"])
@pytest.mark.parametrize("value", [date(2026, 11, 15), "2026-11-15T12:00:00"])
def test_selected_date_is_saved_and_can_be_cleared(form, monkeypatch, field, value):
    page = SimpleNamespace(show_dialog=Mock())
    monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
    if field == "prescription":
        choose, clear = form._prescription_button, form._clear_prescription_button
    else:
        form.treatment_end_type.value = "date"
        form.treatment_end_type.on_select(None)
        choose, clear = form._end_button, form._clear_end_button
    choose.on_click(None)
    picker = page.show_dialog.call_args.args[0]
    picker.on_change(SimpleNamespace(control=SimpleNamespace(value=value)))
    selected = form.get_medication()
    actual = selected.prescription_date if field == "prescription" else selected.treatment_end.end_date
    assert actual == date(2026, 11, 15)

    clear.on_click(None)
    if field == "prescription":
        assert form.get_medication().prescription_date is None
    else:
        with pytest.raises(ValueError, match="Select a calendar date for the treatment end"):
            form.get_medication()


def test_choosing_a_non_date_end_option_does_not_save_the_previous_end_date():
    form = MedicationForm(Medication(
        name="Medication", treatment_end=TreatmentEnd("date", date(2026, 12, 1)),
    ))
    form.treatment_end_type.value = "no_end_date"
    form.treatment_end_type.on_select(None)

    assert form.get_medication().treatment_end == TreatmentEnd("no_end_date")


@pytest.mark.parametrize("field,value", [
    ("name_field", "Changed name"), ("notes_field", "Unsaved notes"), ("amount_value", "unfinished number"),
])
def test_form_detects_changes_and_restored_values(form, field, value):
    control = getattr(form, field)
    original = control.value
    control.value = value
    assert form.has_changes()

    control.value = original
    assert not form.has_changes()


def test_removing_and_restoring_a_photo_updates_unsaved_changes():
    form = MedicationForm(Medication(name="Medication", photo=b"original photo"))
    form._remove_photo_button.on_click(None)
    assert form.get_medication().photo is None
    assert form.has_changes()

    form.set_photo(b"original photo")
    assert form.get_medication().photo == b"original photo"
    assert not form.has_changes()


def test_suggested_name_remains_editable():
    form = MedicationForm(Medication(name="Suggested"), suggested_name=True)
    assert not form.name_field.read_only
    form.name_field.value = "Corrected medication name"

    assert form.get_medication().name == "Corrected medication name"
