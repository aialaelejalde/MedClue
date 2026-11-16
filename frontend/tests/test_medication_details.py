"""Test medication details screen behavior."""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest

from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.medications import Amount, FoodInstructions, Frequency, Medication, TreatmentEnd
from medclue_mobile.ui import dialogs
from medclue_mobile.ui.screens import medication_details
from medclue_mobile.ui.screens.medication_details import MedicationDetailsScreen


ASYNC_OPERATION_TIMEOUT_SECONDS = 5


@pytest.fixture
def details_context(monkeypatch):
    page = SimpleNamespace()
    monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
    cabinet = Mock(spec=MedicationCabinet)
    edit = AsyncMock()
    deleted = AsyncMock()
    screen = MedicationDetailsScreen(cabinet, Medication(id=1, name="Saved medication"), edit, deleted)
    return SimpleNamespace(screen=screen, cabinet=cabinet, edit=edit, deleted=deleted, page=page)


def displayed_text(control):
    if isinstance(control, ft.Text):
        yield control.value
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from displayed_text(content)
    for child in getattr(control, "controls", []):
        yield from displayed_text(child)


@pytest.mark.parametrize("field,value,expected", [
    ("amount", Amount(type="quantity", value=1.0, unit="tablets"), "1 Tablet(s)"),
    ("amount", Amount(type="quantity", value=1.5, unit="mL"), "1.5 mL"),
    ("amount", Amount(type="custom", text=" Half a tablet "), " Half a tablet "),
    ("frequency", Frequency(type="interval", value=1.0, unit="hours"), "Every 1 hour"),
    ("frequency", Frequency(type="interval", value=2.0, unit="hours"), "Every 2 hours"),
    ("frequency", Frequency(type="interval", value=1.5, unit="hours"), "Every 1.5 hours"),
    ("frequency", Frequency(type="twice_daily"), "Twice a day"),
    ("frequency", Frequency(type="custom", text=" At bedtime "), " At bedtime "),
    ("food", FoodInstructions(type="with_food"), "With food"),
    ("food", FoodInstructions(type="custom", text=" After breakfast "), " After breakfast "),
])
def test_saved_instructions_keep_their_current_wording(field, value, expected):
    medication = Medication(id=1, name="Saved medication", **{field: value})
    screen = MedicationDetailsScreen(Mock(spec=MedicationCabinet), medication, AsyncMock(), AsyncMock())

    assert expected in list(displayed_text(screen))


@pytest.mark.parametrize("field,value,expected", [
    ("prescription_date", date(2026, 11, 15), "2026-11-15"),
    ("treatment_end", TreatmentEnd("date", date(2026, 12, 1)), "2026-12-01"),
    ("treatment_end", TreatmentEnd("no_end_date"), "No end date was given"),
    ("notes", " First line\nSecond line ", " First line\nSecond line "),
])
def test_saved_dates_and_notes_are_available_in_details(field, value, expected):
    medication = Medication(id=1, name="Saved medication", **{field: value})
    screen = MedicationDetailsScreen(Mock(spec=MedicationCabinet), medication, AsyncMock(), AsyncMock())

    assert expected in list(displayed_text(screen))


def test_saved_uses_are_displayed_in_full():
    uses = ["An official indication (with restrictions and conditions). " * 8, "My personal reason"]
    medication = Medication(id=1, name="Saved medication", uses=uses)
    screen = MedicationDetailsScreen(Mock(spec=MedicationCabinet), medication, AsyncMock(), AsyncMock())

    text = list(displayed_text(screen))
    assert all(use in text for use in uses)
    assert medication.uses == uses


@pytest.mark.parametrize("deleted", [False, True])
def test_delete_callback_runs_only_after_successful_deletion(details_context, monkeypatch, deleted):
    context = details_context
    deletion = AsyncMock(return_value=deleted)
    monkeypatch.setattr(medication_details, "delete_medication_with_confirmation", deletion)

    asyncio.run(context.screen._delete_button.on_click(None))

    deletion.assert_awaited_once()
    if deleted:
        context.deleted.assert_awaited_once_with()
    else:
        context.deleted.assert_not_awaited()
        assert not context.screen._edit_button.disabled
        assert not context.screen._delete_button.disabled


@pytest.mark.parametrize("action", ["edit", "delete"])
def test_pending_action_prevents_other_actions(details_context, monkeypatch, action):
    context = details_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def wait_for_action(*args, **kwargs):
            started.set()
            await release.wait()
            return True

        confirm = AsyncMock(side_effect=wait_for_action)
        monkeypatch.setattr(dialogs, "_show_dialog", confirm)
        context.edit.side_effect = wait_for_action
        button = context.screen._edit_button if action == "edit" else context.screen._delete_button
        task = asyncio.create_task(button.on_click(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            assert context.screen._edit_button.disabled
            assert context.screen._delete_button.disabled
            await context.screen._edit_button.on_click(None)
            await context.screen._delete_button.on_click(None)
            context.cabinet.delete_medication.assert_not_called()
            assert context.edit.await_count == (1 if action == "edit" else 0)
            assert confirm.await_count == (1 if action == "delete" else 0)
        finally:
            release.set()
            await task
        if action == "edit":
            context.edit.assert_awaited_once_with(1)
            assert not context.screen._edit_button.disabled
            assert not context.screen._delete_button.disabled
        else:
            context.cabinet.delete_medication.assert_called_once_with(1)
            context.deleted.assert_awaited_once_with()

    asyncio.run(run())


def test_deleted_medication_cannot_be_edited_or_deleted_again(details_context, monkeypatch):
    context = details_context
    confirm = AsyncMock(return_value=True)
    monkeypatch.setattr(dialogs, "_show_dialog", confirm)

    async def run():
        await context.screen._delete_button.on_click(None)
        await context.screen._edit_button.on_click(None)
        await context.screen._delete_button.on_click(None)

    asyncio.run(run())

    confirm.assert_awaited_once()
    context.cabinet.delete_medication.assert_called_once_with(1)
    context.deleted.assert_awaited_once_with()
    context.edit.assert_not_awaited()
    assert context.screen._edit_button.disabled
    assert context.screen._delete_button.disabled
