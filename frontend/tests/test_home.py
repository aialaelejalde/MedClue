"""Test search, sorting, loading errors, and deletion from the cabinet screen."""

import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import flet as ft
import pytest

from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.medications import Medication
from medclue_mobile.ui import dialogs
from medclue_mobile.ui.screens.home import HomeScreen


ASYNC_OPERATION_TIMEOUT_SECONDS = 5


@pytest.fixture
def home_context(monkeypatch):
    page = SimpleNamespace()
    monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
    medications = [
        Medication(id=1, name="First medication", uses=["Pain"]),
        Medication(id=2, name="Second medication", uses=["Pain"]),
    ]
    cabinet = Mock(spec=MedicationCabinet)
    cabinet.list_medications.return_value = medications
    cabinet.count_medications.return_value = len(medications)
    screen = HomeScreen(cabinet, AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock())
    cabinet.list_medications.reset_mock()
    cabinet.count_medications.reset_mock()
    return SimpleNamespace(screen=screen, cabinet=cabinet, medications=medications)


def delete_action(card):
    menu = card.content.controls[2].content
    return menu.items[2].on_click


def test_search_keeps_the_total_cabinet_count(home_context):
    context = home_context
    context.cabinet.list_medications.return_value = [context.medications[0]]
    context.screen.search_field.value = "First"

    context.screen.search_field.on_change(None)

    context.cabinet.list_medications.assert_called_once_with("First", "recently_added")
    context.cabinet.count_medications.assert_called_once_with()
    assert len(context.screen._medication_list.controls) == 1
    assert context.screen._count.value == "2 medications"
    assert context.screen._medication_list.visible
    assert not context.screen._no_results.visible
    assert not context.screen._empty_state.visible


def test_clearing_an_unsuccessful_search_restores_the_list_and_keeps_sorting(home_context):
    context = home_context
    context.screen._sort_button.items[1].on_click(None)
    context.cabinet.list_medications.return_value = []
    context.screen.search_field.value = "No match"
    context.screen.search_field.on_change(None)
    assert context.screen._no_results.visible
    assert not context.screen._empty_state.visible
    assert not context.screen._medication_list.visible

    context.cabinet.list_medications.side_effect = None
    context.cabinet.list_medications.return_value = context.medications
    context.cabinet.list_medications.reset_mock()
    context.screen._no_results.controls[1].on_click(None)

    context.cabinet.list_medications.assert_called_once_with("", "name_az")
    assert context.screen.search_field.value == ""
    assert context.screen._sort_label.value == "Name A-Z"
    assert context.screen._medication_list.visible
    assert len(context.screen._medication_list.controls) == 2
    assert not context.screen._no_results.visible


def test_changing_sort_order_keeps_the_search(home_context):
    context = home_context
    context.screen.search_field.value = "pain"

    context.screen._sort_button.items[1].on_click(None)

    context.cabinet.list_medications.assert_called_once_with("pain", "name_az")
    assert context.screen.search_field.value == "pain"
    assert context.screen._sort_label.value == "Name A-Z"
    assert len(context.screen._medication_list.controls) == 2


@pytest.mark.parametrize("error", [sqlite3.OperationalError("unavailable"), OSError(), ValueError()])
def test_retry_after_a_loading_error_restores_the_list(home_context, error):
    context = home_context
    context.cabinet.list_medications.side_effect = error
    context.screen.search_field.on_change(None)
    assert context.screen._medication_list.controls[0].value == "Cannot load medications"
    assert not context.screen._empty_state.visible
    assert not context.screen._no_results.visible
    retry_button = context.screen._medication_list.controls[-1]

    context.cabinet.list_medications.side_effect = None
    context.cabinet.list_medications.reset_mock()
    retry_button.on_click(None)

    context.cabinet.list_medications.assert_called_once_with("", "recently_added")
    assert len(context.screen._medication_list.controls) == 2
    assert context.screen._count.value == "2 medications"
    assert context.screen._medication_list.visible


@pytest.mark.parametrize("confirm", [False, True])
def test_delete_refreshes_only_after_confirmation_and_keeps_filters(home_context, monkeypatch, confirm):
    context = home_context
    confirmation = AsyncMock(return_value=confirm)
    monkeypatch.setattr(dialogs, "_show_dialog", confirmation)
    context.screen.search_field.value = "pain"
    context.screen._sort_button.items[1].on_click(None)
    delete = delete_action(context.screen._medication_list.controls[0])
    context.cabinet.list_medications.return_value = [context.medications[1]]
    context.cabinet.count_medications.return_value = 1
    context.cabinet.list_medications.reset_mock()

    asyncio.run(delete(None))

    confirmation.assert_awaited_once()
    if confirm:
        context.cabinet.delete_medication.assert_called_once_with(1)
        context.cabinet.list_medications.assert_called_once_with("pain", "name_az")
        assert len(context.screen._medication_list.controls) == 1
        assert context.screen._count.value == "1 medication"
    else:
        context.cabinet.delete_medication.assert_not_called()
        context.cabinet.list_medications.assert_not_called()
        assert len(context.screen._medication_list.controls) == 2
    assert context.screen.search_field.value == "pain"
    assert context.screen._sort_label.value == "Name A-Z"


def test_pending_delete_blocks_another_confirmation_and_releases_after_cancellation(home_context, monkeypatch):
    context = home_context

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def wait_for_confirmation(*args, **kwargs):
            started.set()
            await release.wait()
            return False

        confirmation = AsyncMock(side_effect=wait_for_confirmation)
        monkeypatch.setattr(dialogs, "_show_dialog", confirmation)
        first_delete, second_delete = [delete_action(card) for card in context.screen._medication_list.controls]
        task = asyncio.create_task(first_delete(None))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            await second_delete(None)
            confirmation.assert_awaited_once()
            context.cabinet.delete_medication.assert_not_called()
        finally:
            release.set()
            await task
        await second_delete(None)
        assert confirmation.await_count == 2
        context.cabinet.delete_medication.assert_not_called()

    asyncio.run(run())
