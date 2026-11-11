"""Test navigation between screens with simulated app services."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest

from medclue_mobile import app as app_module
from medclue_mobile.api_client import MedClueApiClient
from medclue_mobile.app import MedClueApp
from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.identification import IdentificationSession
from medclue_mobile.medications import Medication
from medclue_mobile.sqlite_repository import MedicationRepository
from medclue_mobile.ui.screens import add, edit_medication, medication_details
from medclue_mobile.ui.screens.add import AddMedicationScreen
from medclue_mobile.ui.screens.edit_medication import EditMedicationScreen
from medclue_mobile.ui.screens.home import HomeScreen
from medclue_mobile.ui.screens.identification_result import IdentificationResultScreen
from medclue_mobile.ui.screens.identify import IdentifyScreen
from medclue_mobile.ui.screens.identifying_medication import IdentifyingMedicationScreen
from medclue_mobile.ui.screens.medication_details import MedicationDetailsScreen
from medclue_mobile.ui.screens.possible_match_result import PossibleMatchResultScreen
from medclue_mobile.ui.screens.possible_matches import PossibleMatchesScreen


VERIFIED_RESULT = {
    "status": "verified",
    "medication": {"name": "Confirmed medication"},
    "official_uses": ["Official use"],
}


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    page = SimpleNamespace(views=[ft.View()], update=Mock(), show_dialog=Mock())
    page.views[0].confirm_pop = AsyncMock()
    monkeypatch.setattr(ft.Control, "page", property(lambda self: page))

    saved = Medication(id=1, name="Saved medication")
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
    monkeypatch.setattr(add, "confirm_discard_changes", discard)
    monkeypatch.setattr(edit_medication, "confirm_discard_changes", discard)
    monkeypatch.setattr(medication_details, "confirm_delete_medication", delete)
    monkeypatch.setattr(app_module, "confirm_leave_identification", leave)
    for module in (app_module, add, edit_medication, medication_details):
        monkeypatch.setattr(module, "show_error", error)

    app = MedClueApp(page, "https://backend.example.invalid", database_path=tmp_path / "medclue.db")
    return SimpleNamespace(
        app=app, page=page, cabinet=cabinet, saved=saved, session=session,
        discard=discard, leave=leave, delete=delete, error=error,
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
    assert app._screen is app._view.controls[0]
    assert app._view.navigation_bar is app._navigation
    assert app._navigation.selected_index == tab
    assert app._view.can_pop is (screen_type is HomeScreen)


def test_app_starts_on_home(app_context):
    async def run():
        await app_context.app.start()
        assert_screen(app_context.app, HomeScreen, 0)
        assert [item.label for item in app_context.app._navigation.destinations] == ["Home", "Identify", "Add"]
        app_context.session.identify.assert_not_awaited()
    asyncio.run(run())


@pytest.mark.parametrize("platform", [ft.PagePlatform.ANDROID, ft.PagePlatform.WINDOWS])
def test_start_opens_home_without_a_python_logo_or_artificial_delay(app_context, monkeypatch, platform):
    app_context.page.platform = platform

    def check_first_frame():
        assert_screen(app_context.app, HomeScreen, 0)
        app_context.session.identify.assert_not_awaited()

    app_context.page.update.side_effect = check_first_frame
    delay = AsyncMock()
    monkeypatch.setattr(app_module.asyncio, "sleep", delay)

    asyncio.run(app_context.app.start())

    delay.assert_not_awaited()
    app_context.page.update.assert_called_once()
    assert_screen(app_context.app, HomeScreen, 0)


def test_photo_dialog_fills_its_frame_without_distorting_the_camera(app_context, monkeypatch):
    photos = SimpleNamespace(
        camera=ft.Container(), initialize_camera=AsyncMock(),
        capture=AsyncMock(return_value=b"new photo"), discard_photo=Mock(),
    )
    monkeypatch.setattr(app_module, "PhotoManager", lambda: photos)
    app_context.page.width = 390
    app_context.page.pop_dialog = Mock()
    monkeypatch.setattr(ft.Control, "update", Mock())

    async def run():
        task = asyncio.create_task(app_context.app._take_photo())
        await asyncio.sleep(0)
        dialog = app_context.page.show_dialog.call_args.args[0]
        frame, actions = dialog.content.content.controls
        assert actions.controls[0].expand
        frame.on_size_change(SimpleNamespace(width=280, height=210))
        assert photos.camera.width == pytest.approx(280)
        assert photos.camera.height == pytest.approx(280 / (3 / 4))
        assert photos.camera.top < 0

        photos.camera.on_state_change(SimpleNamespace(
            aspect_ratio=16 / 9, device_orientation=ft.DeviceOrientation.LANDSCAPE_LEFT,
            locked_capture_orientation=None, preview_pause_orientation=None,
        ))
        assert photos.camera.width == pytest.approx(210 * 16 / 9)
        assert photos.camera.height == pytest.approx(210)
        assert photos.camera.left < 0

        await actions.controls[0].on_click(None)
        assert await task == b"new photo"
        photos.discard_photo.assert_called_once()

    asyncio.run(run())


def test_navigation_only_keeps_floating_actions_on_details_and_edit(app_context):
    async def run():
        app = app_context.app
        await app.start()
        assert app._view.floating_action_button is None
        await app._open_details(1)
        assert app._view.floating_action_button is app._screen._edit_button
        await app._open_edit(1)
        assert app._view.floating_action_button is app._screen._save_button
        await app._open_add()
        assert app._view.floating_action_button is None

    asyncio.run(run())


def test_open_medication_edit_and_return_to_details(app_context):
    async def run():
        app = app_context.app
        await app.start()
        await app._screen._medication_list.controls[0].on_click(None)
        assert_screen(app, MedicationDetailsScreen, 0)
        await app._screen._edit_button.on_click(None)
        assert_screen(app, EditMedicationScreen, 0)
        await press_back(app)
        assert_screen(app, MedicationDetailsScreen, 0)
        assert app._screen._medication.id == app_context.saved.id
        app_context.discard.assert_not_awaited()
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


@pytest.mark.parametrize("confirm", [False, True])
def test_delete_returns_home_only_after_confirmation(app_context, confirm):
    async def run():
        app = app_context.app
        await app.start()
        await app._screen._medication_list.controls[0].on_click(None)
        details = app._screen
        app_context.delete.return_value = confirm
        await details._delete_button.on_click(None)
        app_context.delete.assert_awaited_once_with(app_context.page)
        if confirm:
            app_context.cabinet.delete_medication.assert_called_once_with(app_context.saved.id)
            assert_screen(app, HomeScreen, 0)
        else:
            app_context.cabinet.delete_medication.assert_not_called()
            assert app._screen is details
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
        app_context.discard.assert_not_awaited()
    asyncio.run(run())


@pytest.mark.parametrize("index,screen_type", [(0, HomeScreen), (1, IdentifyScreen), (2, AddMedicationScreen)])
def test_main_navigation_opens_the_selected_section(app_context, index, screen_type):
    async def run():
        await app_context.app.start()
        await select_tab(app_context.app, index)
        assert_screen(app_context.app, screen_type, index)
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


@pytest.mark.parametrize("button_index,screen_type,tab", [(1, IdentifyScreen, 1), (2, AddMedicationScreen, 2)])
def test_empty_cabinet_buttons_open_the_corresponding_section(app_context, button_index, screen_type, tab):
    async def run():
        app_context.cabinet.list_medications.return_value = []
        await app_context.app.start()
        actions = app_context.app._screen._empty_state.controls[1].controls
        await actions[button_index - 1].on_click(None)
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


@pytest.mark.parametrize("result,screen_type", [
    (VERIFIED_RESULT, IdentificationResultScreen),
    ({"status": "multiple_matches", "candidates": [{"name": "First"}, {"name": "Second"}]}, PossibleMatchesScreen),
    ({"status": "multiple_matches", "presentations": [
        {"name": "First", "national_code": "1"}, {"name": "Second", "national_code": "2"},
    ]}, PossibleMatchesScreen),
    ({"status": "not_identified"}, PossibleMatchResultScreen),
    ({"status": "no_match", "suggested_candidate": {"name": "Suggested"}}, PossibleMatchResultScreen),
    ({"status": "connection_error", "failed_step": "image_analysis"}, PossibleMatchResultScreen),
    ({"status": "timeout", "failed_step": "cima_verification"}, PossibleMatchResultScreen),
])
def test_identification_result_opens_correct_screen_and_back_returns_to_camera(app_context, result, screen_type):
    async def run():
        app = app_context.app
        app_context.session.identify.return_value = result
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        assert_screen(app, screen_type, 1)
        app_context.error.assert_not_awaited()
        await press_back(app)
        assert_screen(app, IdentifyScreen, 1)
        app_context.discard.assert_not_awaited()
        app_context.leave.assert_not_awaited()
        app_context.cabinet.save_medication.assert_not_called()
    asyncio.run(run())


@pytest.mark.parametrize("tab,screen_type", [(0, HomeScreen), (1, IdentifyScreen), (2, AddMedicationScreen)])
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


def test_verified_save_button_opens_add_instead_of_saving_automatically(app_context):
    async def run():
        app = app_context.app
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        await app._screen._save_button.on_click(None)
        assert_screen(app, AddMedicationScreen, 2)
        assert app._screen.form.name_field.value == "Confirmed medication"
        assert not any(option.value for option in app._screen.form._use_options)
        app_context.cabinet.save_medication.assert_not_called()
    asyncio.run(run())


@pytest.mark.parametrize("action", ["cancel", "back", "tab"])
def test_cancelled_identification_cannot_display_a_late_result(app_context, action):
    async def run():
        app = app_context.app
        started = asyncio.Event()
        release = asyncio.Event()

        async def late_result(photo, media_type):
            started.set()
            await release.wait()
            return VERIFIED_RESULT

        app_context.session.identify.side_effect = late_result
        app_context.leave.return_value = True
        await app.start()
        await select_tab(app, 1)
        app_context.session.cancel.reset_mock()
        task = asyncio.create_task(app._screen._on_identify(b"captured photo", "image/jpeg"))
        try:
            await started.wait()
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
            await started.wait()
            await select_tab(app, 2)
            assert_screen(app, IdentifyingMedicationScreen, 1)
            app_context.leave.assert_awaited_once_with(app_context.page)
            app_context.session.cancel.assert_not_called()
        finally:
            release.set()
            await task
        assert_screen(app, IdentificationResultScreen, 1)
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
        app_context.session.identify.return_value = {"status": "timeout", "failed_step": "cima_verification"}
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
        assert_screen(app, AddMedicationScreen, 2)
        form = app._screen.form
        assert form.name_field.label == "Suggested name"
        assert form.name_field.value == "Suggested medication"
        assert not form.name_field.read_only
        assert form.get_medication().photo == b"captured photo"
        form.name_field.value = "Corrected medication name"
        draft = form.get_medication()
        assert draft.name == "Corrected medication name"
        assert draft.photo == b"captured photo"
        assert draft.uses == []
        app_context.cabinet.save_medication.assert_not_called()
    asyncio.run(run())
