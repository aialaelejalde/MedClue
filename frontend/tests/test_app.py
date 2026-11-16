"""Test navigation between screens with simulated app services."""

import asyncio
import sqlite3
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest

from medclue_mobile import app as app_module
from medclue_mobile.api_client import ApiError, MedClueApiClient
from medclue_mobile.app import MedClueApp
from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.identification import IdentificationSession
from medclue_mobile.medications import Medication
from medclue_mobile.sqlite_repository import MedicationRepository
from medclue_mobile.ui import dialogs
from medclue_mobile.ui.screens import medication_editor
from medclue_mobile.ui.screens.home import HomeScreen
from medclue_mobile.ui.screens.identification_result import IdentificationResultScreen
from medclue_mobile.ui.screens.identify import IdentifyScreen
from medclue_mobile.ui.screens.identifying_medication import IdentifyingMedicationScreen
from medclue_mobile.ui.screens.medication_details import MedicationDetailsScreen
from medclue_mobile.ui.screens.medication_editor import MedicationEditorScreen
from medclue_mobile.ui.screens.possible_match_result import PossibleMatchResultScreen
from medclue_mobile.ui.screens.possible_matches import PossibleMatchesScreen


VERIFIED_RESULT = {
    "status": "verified",
    "medication": {"name": "Confirmed medication"},
    "official_uses": ["Official use"],
}
ASYNC_OPERATION_TIMEOUT_SECONDS = 5


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    page = SimpleNamespace(views=[ft.View()], update=Mock(), show_dialog=Mock())
    page.views[0].confirm_pop = AsyncMock()
    monkeypatch.setattr(ft.Control, "page", property(lambda self: page))

    saved = Medication(id=1, name="Saved medication", strength="500 mg", form="tablet")
    cabinet = Mock(spec=MedicationCabinet)
    cabinet.list_medications.return_value = [saved]
    cabinet.get_medication.return_value = saved
    cabinet.save_medication.return_value = saved
    repository = Mock(spec=MedicationRepository)
    monkeypatch.setattr(app_module, "MedicationRepository", Mock(return_value=repository))
    monkeypatch.setattr(app_module, "MedicationCabinet", Mock(return_value=cabinet))

    client = Mock(spec=MedClueApiClient)
    session = Mock(spec=IdentificationSession)
    session.photo = b"captured photo"
    session.identify = AsyncMock(return_value=VERIFIED_RESULT)
    session.select_match = AsyncMock(return_value=VERIFIED_RESULT)
    session.retry = AsyncMock(return_value=VERIFIED_RESULT)
    monkeypatch.setattr(app_module, "MedClueApiClient", Mock(return_value=client))
    monkeypatch.setattr(app_module, "IdentificationSession", Mock(return_value=session))
    monkeypatch.setattr(app_module, "PhotoManager", Mock(side_effect=lambda: SimpleNamespace(camera=ft.Container())))

    discard = AsyncMock(return_value=False)
    leave = AsyncMock(return_value=False)
    delete = AsyncMock(return_value=False)
    error = AsyncMock(return_value=False)
    monkeypatch.setattr(medication_editor, "confirm_discard_changes", discard)
    monkeypatch.setattr(dialogs, "_show_dialog", delete)
    monkeypatch.setattr(app_module, "confirm_leave_identification", leave)
    for module in (app_module, medication_editor, dialogs):
        monkeypatch.setattr(module, "show_error", error)

    app = MedClueApp(page, "https://backend.example.invalid", database_path=tmp_path / "medclue.db")
    return SimpleNamespace(
        app=app, page=page, cabinet=cabinet, saved=saved, session=session,
        discard=discard, leave=leave, delete=delete, error=error, client=client, repository=repository,
    )


async def select_tab(app, index):
    app._navigation.selected_index = index
    await app._navigation.on_change(SimpleNamespace(control=app._navigation))


async def press_back(app):
    await app._view.on_confirm_pop(SimpleNamespace(control=app._view))


async def open_edit_from_home(app):
    await app._screen._medication_list.controls[0].on_click(None)
    await app._screen._edit_button.on_click(None)


def assert_screen(app, screen_type, tab):
    assert isinstance(app._view.controls[0], screen_type)
    assert app._navigation.selected_index == tab
    assert app._view.can_pop is (screen_type is HomeScreen)


def test_app_starts_on_home(app_context):
    async def run():
        await app_context.app.start()
        assert_screen(app_context.app, HomeScreen, 0)
        assert [item.label for item in app_context.app._navigation.destinations] == ["Home", "Identify", "Add"]
        app_context.session.identify.assert_not_awaited()
        app_module.MedClueApiClient.assert_not_called()
    asyncio.run(run())


@pytest.mark.parametrize("action,title,screen_type", [
    ("_open_details", "Cannot open medication", MedicationDetailsScreen),
    ("_open_edit", "Cannot edit medication", MedicationEditorScreen),
])
@pytest.mark.parametrize("failure", [LookupError("Missing record"), sqlite3.OperationalError("Unavailable")])
def test_failed_record_lookup_keeps_home_available_and_allows_another_attempt(
    app_context, action, title, screen_type, failure,
):
    context = app_context

    async def run():
        await context.app.start()
        home = context.app._screen
        context.cabinet.get_medication.side_effect = failure

        await getattr(context.app, action)(context.saved.id)

        context.error.assert_awaited_once_with(
            context.page, title, "We couldn't load this medication. Please try again.",
        )
        assert context.app._screen is home
        assert_screen(context.app, HomeScreen, 0)
        context.cabinet.save_medication.assert_not_called()
        context.cabinet.delete_medication.assert_not_called()

        context.cabinet.get_medication.side_effect = None
        await getattr(context.app, action)(context.saved.id)
        assert_screen(context.app, screen_type, 0)
        assert context.app._medication_id == context.saved.id

    asyncio.run(run())


@pytest.mark.parametrize("retry", [False, True])
def test_storage_initialization_error_respects_the_retry_choice(app_context, retry):
    context = app_context
    context.repository.initialize.side_effect = [sqlite3.OperationalError("Storage unavailable"), None]
    context.error.return_value = retry

    asyncio.run(context.app.start())

    context.error.assert_awaited_once()
    assert context.error.await_args.args[:3] == (
        context.page, "Cannot open medicine cabinet",
        "We couldn't open your saved medications. Please try again.",
    )
    assert context.repository.initialize.call_count == (2 if retry else 1)
    if retry:
        assert_screen(context.app, HomeScreen, 0)
    else:
        assert context.app._view.controls == []
    app_module.MedClueApiClient.assert_not_called()


def test_closing_events_close_services_only_once_and_prevent_navigation(app_context):
    context = app_context

    async def run():
        await context.app.start()
        await select_tab(context.app, 1)
        context.session.cancel.reset_mock()
        context.page.update.reset_mock()

        await context.page.on_close(None)
        await context.page.on_disconnect(None)
        await context.page.on_app_lifecycle_state_change(SimpleNamespace(state=ft.AppLifecycleState.DETACH))

        context.session.cancel.assert_called_once_with()
        context.client.close.assert_awaited_once_with()
        await select_tab(context.app, 0)
        context.page.update.assert_not_called()

    asyncio.run(run())


def test_closing_app_ends_the_pending_photo_dialog(app_context, monkeypatch):
    context = app_context
    dialog = Mock(spec=app_module.PhotoCaptureDialog)
    monkeypatch.setattr(app_module, "PhotoCaptureDialog", Mock(return_value=dialog))

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def take_photo():
            started.set()
            await release.wait()
            return None

        dialog.open.side_effect = take_photo
        dialog.close.side_effect = release.set
        await context.app.start()
        await select_tab(context.app, 2)
        task = asyncio.create_task(context.app._screen._on_take_photo())
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            await context.page.on_close(None)
        finally:
            release.set()
            result = await task
        assert result is None
        dialog.close.assert_called_once_with()

    asyncio.run(run())


@pytest.mark.parametrize("index,screen_type", [(0, HomeScreen), (1, IdentifyScreen), (2, MedicationEditorScreen)])
def test_main_navigation_opens_the_selected_section(app_context, index, screen_type):
    async def run():
        await app_context.app.start()
        await select_tab(app_context.app, index)
        assert_screen(app_context.app, screen_type, index)
        if screen_type is MedicationEditorScreen:
            assert not app_context.app._screen.is_editing
    asyncio.run(run())


@pytest.mark.parametrize("action,screen_type", [
    ("card", MedicationDetailsScreen),
    ("view_menu", MedicationDetailsScreen),
    ("edit_menu", MedicationEditorScreen),
])
def test_medication_card_or_menu_opens_the_selected_screen(app_context, action, screen_type):
    async def run():
        app = app_context.app
        await app.start()
        card = app._screen._medication_list.controls[0]
        if action == "card":
            await card.on_click(None)
        else:
            menu = card.content.controls[2].content
            await menu.items[0 if action == "view_menu" else 1].on_click(None)
        assert_screen(app, screen_type, 0)
        if screen_type is MedicationEditorScreen:
            assert app._screen.is_editing
        app_context.cabinet.get_medication.assert_called_once_with(app_context.saved.id)
    asyncio.run(run())


@pytest.mark.parametrize("screen_type,tab", [(IdentifyScreen, 1), (MedicationEditorScreen, 2)])
def test_empty_cabinet_buttons_open_the_corresponding_section(app_context, screen_type, tab):
    async def run():
        app_context.cabinet.list_medications.return_value = []
        await app_context.app.start()
        screen = app_context.app._screen
        actions = screen._empty_state.content.controls[1].controls
        await actions[1 if tab == 1 else 0].controls[0].on_click(None)
        assert_screen(app_context.app, screen_type, tab)
    asyncio.run(run())


@pytest.mark.parametrize("source", ["details", "identify"])
def test_android_back_from_details_or_camera_returns_home(app_context, source):
    async def run():
        app = app_context.app
        await app.start()
        if source == "details":
            await app._screen._medication_list.controls[0].on_click(None)
        else:
            await select_tab(app, 1)
        await press_back(app)
        assert_screen(app, HomeScreen, 0)
        app_context.leave.assert_not_awaited()
    asyncio.run(run())


def test_successful_deletion_returns_home(app_context):
    async def run():
        app = app_context.app
        await app.start()
        await app._screen._medication_list.controls[0].on_click(None)
        app_context.delete.return_value = True
        await app._screen._delete_button.on_click(None)
        app_context.cabinet.delete_medication.assert_called_once_with(app_context.saved.id)
        assert_screen(app, HomeScreen, 0)
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["add", "edit"])
def test_successful_save_opens_updated_details(app_context, mode):
    async def run():
        app = app_context.app
        await app.start()
        if mode == "add":
            await select_tab(app, 2)
        else:
            await open_edit_from_home(app)
        app._screen.form.name_field.value = "Updated name"
        saved = replace(app_context.saved, name="Updated name")
        app_context.cabinet.save_medication.return_value = saved
        await app._screen._save_button.on_click(None)
        assert_screen(app, MedicationDetailsScreen, 0)
        assert app._screen._medication == saved
        app_context.cabinet.save_medication.assert_called_once()
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["add", "edit"])
@pytest.mark.parametrize("action", ["tab", "back"])
@pytest.mark.parametrize("discard", [False, True])
def test_leaving_modified_form_respects_confirmation(app_context, mode, action, discard):
    async def run():
        app = app_context.app
        await app.start()
        if mode == "add":
            await select_tab(app, 2)
        else:
            await open_edit_from_home(app)
        form = app._screen
        form.form.notes_field.value = "Unsaved notes"
        app_context.discard.return_value = discard
        if action == "tab":
            await select_tab(app, 0)
        else:
            await press_back(app)
        app_context.discard.assert_awaited_once_with(app_context.page)
        if not discard:
            assert app._screen is form
            assert form.form.notes_field.value == "Unsaved notes"
            assert app._navigation.selected_index == (2 if mode == "add" else 0)
        else:
            destination = MedicationDetailsScreen if mode == "edit" and action == "back" else HomeScreen
            assert_screen(app, destination, 0)
        app_context.cabinet.save_medication.assert_not_called()
    asyncio.run(run())


@pytest.mark.parametrize("mode", ["add", "edit"])
@pytest.mark.parametrize("action", ["tab", "back"])
def test_leaving_unchanged_form_does_not_ask_for_confirmation(app_context, mode, action):
    async def run():
        app = app_context.app
        await app.start()
        if mode == "add":
            await select_tab(app, 2)
        else:
            await open_edit_from_home(app)
        if action == "tab":
            await select_tab(app, 0)
        else:
            await press_back(app)
        destination = MedicationDetailsScreen if mode == "edit" and action == "back" else HomeScreen
        assert_screen(app, destination, 0)
        if destination is MedicationDetailsScreen:
            assert app._screen._medication.id == app_context.saved.id
        app_context.discard.assert_not_awaited()
    asyncio.run(run())


def test_reselecting_add_keeps_the_current_form(app_context):
    async def run():
        app = app_context.app
        await app.start()
        await select_tab(app, 2)
        form = app._screen
        form.form.notes_field.value = "Keep this draft"
        await select_tab(app, 2)
        assert app._screen is form
        assert form.form.notes_field.value == "Keep this draft"
        app_context.discard.assert_not_awaited()
    asyncio.run(run())


@pytest.mark.parametrize("photo", [b"new photo", None])
@pytest.mark.parametrize("navigation", ["tab", "back"])
def test_photo_dialog_blocks_navigation_until_it_returns(app_context, monkeypatch, photo, navigation):
    context = app_context
    dialog = Mock(spec=app_module.PhotoCaptureDialog)
    create_dialog = Mock(return_value=dialog)
    monkeypatch.setattr(app_module, "PhotoCaptureDialog", create_dialog)

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def take_photo():
            started.set()
            await release.wait()
            return photo

        dialog.open.side_effect = take_photo
        await context.app.start()
        await select_tab(context.app, 2)
        editor = context.app._screen
        task = asyncio.create_task(editor._on_take_photo())
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            if navigation == "tab":
                await select_tab(context.app, 0)
            else:
                await press_back(context.app)
            assert context.app._screen is editor
            assert context.app._navigation.selected_index == 2
            context.discard.assert_not_awaited()
        finally:
            release.set()
            result = await task
        assert result == photo
        create_dialog.assert_called_once_with(context.page)
        dialog.open.assert_awaited_once_with()
        await select_tab(context.app, 0)
        assert_screen(context.app, HomeScreen, 0)

    asyncio.run(run())


@pytest.mark.parametrize("result,screen_type", [
    (VERIFIED_RESULT, IdentificationResultScreen),
    ({"status": "multiple_matches", "candidates": [{"name": "First"}, {"name": "Second"}]}, PossibleMatchesScreen),
    ({"status": "multiple_matches", "presentations": [
        {"name": "First", "national_code": "1"}, {"name": "Second", "national_code": "2"},
    ]}, PossibleMatchesScreen),
    ({"status": "not_identified"}, PossibleMatchResultScreen),
    ({"status": "no_match", "suggested_candidate": {
        "name": "Suggested", "strength": "100 mg", "form": "Comprimidos recubiertos",
    }}, PossibleMatchResultScreen),
    ({"status": "connection_error", "failed_step": "image_analysis"}, PossibleMatchResultScreen),
    ({"status": "timeout", "failed_step": "cima_verification", "suggested_candidate": {
        "name": "Suggested", "strength": None, "form": "Comprimidos recubiertos",
    }}, PossibleMatchResultScreen),
])
def test_identification_result_opens_the_correct_screen(app_context, result, screen_type):
    async def run():
        app = app_context.app
        app_context.session.identify.return_value = result
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        assert_screen(app, screen_type, 1)
        app_context.error.assert_not_awaited()
        app_context.cabinet.save_medication.assert_not_called()
    asyncio.run(run())


@pytest.mark.parametrize("result,screen_type", [
    (VERIFIED_RESULT, IdentificationResultScreen),
    ({"status": "multiple_matches", "candidates": [{"name": "First"}, {"name": "Second"}]}, PossibleMatchesScreen),
    ({"status": "not_identified"}, PossibleMatchResultScreen),
])
def test_back_from_result_returns_to_camera_without_confirmation(app_context, result, screen_type):
    async def run():
        app = app_context.app
        app_context.session.identify.return_value = result
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        assert_screen(app, screen_type, 1)

        await press_back(app)

        assert_screen(app, IdentifyScreen, 1)
        app_context.discard.assert_not_awaited()
        app_context.leave.assert_not_awaited()
    asyncio.run(run())


@pytest.mark.parametrize("tab,screen_type", [(0, HomeScreen), (1, IdentifyScreen), (2, MedicationEditorScreen)])
def test_leaving_completed_result_needs_no_confirmation(app_context, tab, screen_type):
    async def run():
        app = app_context.app
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        await select_tab(app, tab)
        assert_screen(app, screen_type, tab)
        app_context.discard.assert_not_awaited()
        app_context.leave.assert_not_awaited()
    asyncio.run(run())


def test_verified_uses_failure_can_retry_from_the_result_screen(app_context):
    async def run():
        context = app_context
        context.session.identify.return_value = {
            "status": "verified", "medication": {"name": "Confirmed medication"},
            "official_uses": [], "failed_step": "uses_translation", "retry_token": "signed-token",
        }
        await context.app.start()
        await select_tab(context.app, 1)
        await context.app._screen._on_identify(b"photo", "image/jpeg")
        assert_screen(context.app, IdentificationResultScreen, 1)
        assert context.app._screen._retry_button.visible
        await context.app._screen._retry_button.on_click(None)
        context.session.retry.assert_awaited_once_with()
        assert_screen(context.app, IdentificationResultScreen, 1)
        assert context.app._screen._official_uses == ["Official use"]
        assert not context.app._screen._retry_button.visible
        context.error.assert_not_awaited()

    asyncio.run(run())


def test_verified_save_button_opens_add_instead_of_saving_automatically(app_context):
    async def run():
        app = app_context.app
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        result_screen = app._screen
        await app._screen._save_button.on_click(None)
        assert_screen(app, MedicationEditorScreen, 2)
        form = app._screen.form
        assert form.get_medication() == result_screen._medication
        assert form._official_uses == result_screen._official_uses
        app_context.cabinet.save_medication.assert_not_called()
    asyncio.run(run())


def test_selecting_candidate_checks_its_index_and_opens_the_result(app_context):
    async def run():
        app = app_context.app
        app_context.session.identify.return_value = {
            "status": "multiple_matches",
            "candidates": [{"name": "First candidate"}, {"name": "Second candidate"}],
        }
        app_context.session.select_match.return_value = {
            "status": "verified", "medication": {"name": "Selected medication"}, "official_uses": [],
        }
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        assert_screen(app, PossibleMatchesScreen, 1)
        await app._screen._match_list.controls[1].on_click(None)
        app_context.session.select_match.assert_awaited_once_with(1)
        assert_screen(app, IdentificationResultScreen, 1)
        assert app._screen._medication.name == "Selected medication"
        app_context.error.assert_not_awaited()
    asyncio.run(run())


def test_try_again_retries_the_session_and_opens_the_result(app_context):
    async def run():
        app = app_context.app
        app_context.session.identify.return_value = {
            "status": "timeout", "failed_step": "cima_verification",
            "suggested_candidate": {"name": "Suggested", "strength": "100 mg", "form": None},
        }
        app_context.session.retry.return_value = {
            "status": "verified", "medication": {"name": "Retried medication"}, "official_uses": [],
        }
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        assert_screen(app, PossibleMatchResultScreen, 1)
        await app._screen._retry_button.on_click(None)
        app_context.session.retry.assert_awaited_once_with()
        assert_screen(app, IdentificationResultScreen, 1)
        assert app._screen._medication.name == "Retried medication"
        app_context.error.assert_not_awaited()
    asyncio.run(run())


def test_manual_entry_from_unconfirmed_result_keeps_photo_and_editable_suggested_name(app_context):
    async def run():
        app = app_context.app
        app_context.session.identify.return_value = {
            "status": "no_match", "suggested_candidate": {"name": "Suggested medication"},
        }
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        assert_screen(app, PossibleMatchResultScreen, 1)
        await app._screen._add_button.on_click(None)
        assert_screen(app, MedicationEditorScreen, 2)
        form = app._screen.form
        assert form.name_field.label == "Suggested name"
        assert form.name_field.value == "Suggested medication"
        assert form.get_medication().photo == b"captured photo"
        app_context.cabinet.save_medication.assert_not_called()
    asyncio.run(run())


def test_identification_error_shows_message_and_returns_to_camera(app_context):
    async def run():
        app = app_context.app
        app_context.session.identify.side_effect = ApiError("Identification failed")
        await app.start()
        await select_tab(app, 1)
        app_context.session.cancel.reset_mock()

        await app._screen._on_identify(b"captured photo", "image/jpeg")

        app_context.error.assert_awaited_once_with(
            app_context.page, "Identification unavailable",
            "We couldn't complete identification. Please take another photo.",
        )
        assert_screen(app, IdentifyScreen, 1)
        app_context.session.cancel.assert_called_once_with()

    asyncio.run(run())


@pytest.mark.parametrize("action", ["cancel", "back", "tab"])
@pytest.mark.parametrize("late_error", [False, True])
def test_cancelled_identification_ignores_late_results_and_errors(app_context, action, late_error):
    async def run():
        app = app_context.app
        started = asyncio.Event()
        release = asyncio.Event()

        async def late_result(photo, media_type):
            started.set()
            await release.wait()
            if late_error:
                raise ApiError("Late identification error")
            return VERIFIED_RESULT

        app_context.session.identify.side_effect = late_result
        app_context.leave.return_value = True
        await app.start()
        await select_tab(app, 1)
        app_context.session.cancel.reset_mock()
        task = asyncio.create_task(app._screen._on_identify(b"captured photo", "image/jpeg"))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            assert_screen(app, IdentifyingMedicationScreen, 1)
            if action == "cancel":
                await app._screen._cancel_button.on_click(None)
            elif action == "back":
                await press_back(app)
            else:
                await select_tab(app, 0)
            destination = HomeScreen if action == "tab" else IdentifyScreen
            tab = 0 if action == "tab" else 1
            assert_screen(app, destination, tab)
            app_context.session.cancel.assert_called_once()
        finally:
            release.set()
            await task
        assert_screen(app, destination, tab)
        app_context.error.assert_not_awaited()
        if action == "tab":
            app_context.leave.assert_awaited_once_with(app_context.page)
        else:
            app_context.leave.assert_not_awaited()
    asyncio.run(run())


def test_keep_identifying_cancels_the_tab_change(app_context):
    async def run():
        app = app_context.app
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_result(photo, media_type):
            started.set()
            await release.wait()
            return VERIFIED_RESULT

        app_context.session.identify.side_effect = delayed_result
        await app.start()
        await select_tab(app, 1)
        app_context.session.cancel.reset_mock()
        task = asyncio.create_task(app._screen._on_identify(b"captured photo", "image/jpeg"))
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
            await select_tab(app, 2)
            assert_screen(app, IdentifyingMedicationScreen, 1)
            app_context.leave.assert_awaited_once_with(app_context.page)
            app_context.session.cancel.assert_not_called()
        finally:
            release.set()
            await task
        assert_screen(app, IdentificationResultScreen, 1)
    asyncio.run(run())
