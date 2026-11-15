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
from medclue_mobile.ui.screens import add, edit_medication
from medclue_mobile.ui import dialogs
from medclue_mobile.ui.screens.add import AddMedicationScreen
from medclue_mobile.ui.screens.edit_medication import EditMedicationScreen
from medclue_mobile.ui.screens.home import HomeScreen
from medclue_mobile.ui.screens.identification_result import IdentificationResultScreen
from medclue_mobile.ui.screens.identify import IdentifyScreen
from medclue_mobile.ui.screens.identifying_medication import IdentifyingMedicationScreen
from medclue_mobile.ui.screens.medication_details import MedicationDetailsScreen
from medclue_mobile.ui.screens.possible_match_result import PossibleMatchResultScreen
from medclue_mobile.ui.screens.possible_matches import PossibleMatchesScreen
from medclue_mobile.ui.theme import BAR_HEIGHT, HEADER_HEIGHT, CARD_COLOR, BLUE_SURFACE


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
    monkeypatch.setattr(add, "confirm_discard_changes", discard)
    monkeypatch.setattr(edit_medication, "confirm_discard_changes", discard)
    monkeypatch.setattr(dialogs, "confirm_delete_medication", delete)
    monkeypatch.setattr(app_module, "confirm_leave_identification", leave)
    for module in (app_module, add, edit_medication, dialogs):
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
        uses = ["Moderate pain (including migraine; age 14+)", "Fever (short term (adults only))", "(Restriction only)"]
        saved = replace(app_context.saved, uses=uses)
        app_context.cabinet.list_medications.return_value = [saved]
        await app_context.app.start()
        assert_screen(app_context.app, HomeScreen, 0)
        card = app_context.app._screen._medication_list.controls[0]
        chips = card.content.controls[1].content.controls[-1]
        assert [chip.content.value for chip in chips._chips] == ["Moderate pain", "Fever"]
        assert [chip.tooltip for chip in chips._chips] == uses[:2]
        assert chips._uses == saved.uses == uses
        chips._widths, chips._counter_width = {"use:0": 120, "use:1": 70}, 20
        chips._available = 150
        chips._fit()
        assert chips._row.controls[-1].value == "+2"
        assert chips._row.controls[-1].tooltip == "\n".join(uses[1:])
        assert [item.label for item in app_context.app._navigation.destinations] == ["Home", "Identify", "Add"]
        app_context.session.identify.assert_not_awaited()
        assert card.content.controls[1].content.controls[1].value == "500 mg · tablet"
        assert app_context.app._screen._count.value == "1 medication"
        assert app_context.app._screen._sort_button.items[0].content.bgcolor == BLUE_SURFACE
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
        frame, actions, _ = dialog.content.content.controls
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


def test_navigation_keeps_shared_bars_and_inline_actions(app_context):
    async def run():
        app = app_context.app
        await app.start()
        assert app._view.floating_action_button is None
        await app._open_details(1)
        assert app._view.floating_action_button is None
        assert app._screen._edit_button.content == "Edit medication"
        assert (app._view.appbar.toolbar_height, app._navigation.height) == (HEADER_HEIGHT, BAR_HEIGHT)
        assert app._view.appbar.bgcolor == app._navigation.bgcolor == CARD_COLOR
        await app._open_edit(1)
        assert app._view.floating_action_button is None
        assert app._screen._save_button.content == "Save medication"
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
        assert app._screen.form.get_medication().strength == "500 mg"
        assert app._screen.form.get_medication().form == "tablet"
        await press_back(app)
        assert_screen(app, MedicationDetailsScreen, 0)
        assert app._screen._medication.id == app_context.saved.id
        await press_back(app)
        card = app._screen._medication_list.controls[0]
        menu = card.content.controls[2].content
        await menu.items[0].on_click(None)
        assert_screen(app, MedicationDetailsScreen, 0)
        await press_back(app)
        menu = app._screen._medication_list.controls[0].content.controls[2].content
        await menu.items[1].on_click(None)
        assert_screen(app, EditMedicationScreen, 0)
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


@pytest.mark.parametrize("screen_type,tab", [(IdentifyScreen, 1), (AddMedicationScreen, 2)])
def test_empty_cabinet_buttons_open_the_corresponding_section(app_context, screen_type, tab):
    async def run():
        app_context.cabinet.list_medications.return_value = []
        await app_context.app.start()
        screen = app_context.app._screen
        assert screen._count.value == "0 medications"
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
def test_identification_result_opens_correct_screen_and_back_returns_to_camera(app_context, result, screen_type):
    async def run():
        app = app_context.app
        app_context.session.identify.return_value = result
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        assert_screen(app, screen_type, 1)
        if isinstance(app._screen, PossibleMatchResultScreen):
            card = app._screen.content.content.controls[0]
            assert card.bgcolor == CARD_COLOR
            information, actions = card.content.controls
            assert isinstance(information, ft.Container) and information.content.tight
            assert [row.controls[0] for row in actions.controls] == ([app._screen._add_button, app._screen._retake_button] if result["status"] == "no_match" else [button for button in (
                app._screen._retry_button, app._screen._retake_button, app._screen._add_button,
            ) if button.visible])
            content = information.content.controls
            assert content[0].controls[0].aspect_ratio == 4 / 3
            badge = content[0].controls[1].content.controls[1]
            assert badge.value == ("Possible match" if result.get("suggested_candidate") else "Not identified")
            if result.get("suggested_candidate"):
                candidate = result["suggested_candidate"]
                details = content[-1].content.controls[0].controls
                assert details[0].value == candidate["name"]
                expected_description = " · ".join(candidate[field] for field in ("strength", "form") if candidate.get(field))
                assert details[1].value == expected_description
                assert content[-1].bgcolor == CARD_COLOR
            assert content[2].max_lines is None
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
        official_uses = ["A long official indication (with restrictions and conditions). " * 8, "Another use", "Unselected use"]
        app_context.session.identify.return_value = {
            **VERIFIED_RESULT, "official_uses": official_uses,
            "medication": {"name": "Confirmed medication", "strength": "500 mg", "form": "tablet"},
        }
        await app.start()
        await select_tab(app, 1)
        await app._screen._on_identify(b"captured photo", "image/jpeg")
        chips = app._screen.content.content.controls[0].content.controls[0].content.controls[-1]
        assert chips.wrap and len(chips.controls) == len(official_uses)
        assert [chip.content.value for chip in chips.controls] == official_uses
        assert all(chip.content.max_lines is None and chip.content.overflow is None for chip in chips.controls)
        await app._screen._save_button.on_click(None)
        assert_screen(app, AddMedicationScreen, 2)
        form = app._screen.form
        assert form.name_field.value == "Confirmed medication"
        assert form.get_medication().strength == "500 mg"
        assert form.get_medication().form == "tablet"
        assert not any(option.value for option in form._use_options)
        assert form.get_medication().uses == []
        assert not form.has_changes()
        selector = form._use_selector
        assert isinstance(selector, ft.ExpansionTile) and selector.maintain_state
        assert selector.title.value == "Select the uses that apply to you"
        assert selector.subtitle.padding.top == 6
        use_list = selector.controls[0]
        assert use_list.height is None
        options = use_list.controls[0]
        options.on_size_change(SimpleNamespace(width=280, height=96))
        assert use_list.height == 96
        options.on_size_change(SimpleNamespace(width=280, height=480))
        assert use_list.height == 240
        rows = options.controls
        assert [row.content.content.value for row in rows] == official_uses
        assert all(row.content.content.max_lines is None for row in rows)
        rows[0].on_click(None)
        rows[1].on_click(None)
        assert form.get_medication().uses == official_uses[:2]
        assert form._use_summary.value == "2 selected"
        assert rows[0].bgcolor == BLUE_SURFACE and rows[0].content.selected
        rows[0].on_click(None)
        assert form.get_medication().uses == [official_uses[1]]
        assert form._use_summary.value == "1 selected"
        assert rows[0].bgcolor == CARD_COLOR and not rows[0].content.selected
        rows[0].on_click(None)
        selector.expanded = True
        selector.expanded = False
        assert form.get_medication().uses == official_uses[:2]
        form._own_reason.value = True
        form._own_reason.on_change(SimpleNamespace(control=form._own_reason))
        assert form._reason_group.visible
        form._reason_fields[0].value = "My own reason"
        draft = form.get_medication()
        assert draft.uses == [*official_uses[:2], "My own reason"]
        app_context.cabinet.get_medication.return_value = replace(draft, id=1)
        await app._open_edit(1)
        assert_screen(app, EditMedicationScreen, 0)
        assert app._screen.form.get_medication().uses == draft.uses
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
        actions = app._screen.content.content.controls[0].content.controls[-1]
        assert isinstance(actions, ft.Column)
        assert [row.controls[0] for row in actions.controls] == [app._screen._retake_button, app._screen._add_button]
        assert actions.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
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
        content = app._screen.content.content.controls[0].content.controls[0].content.controls
        assert content[-1].content.controls[0].controls[1].value == "100 mg"
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
        content = app._screen.content.content.controls[0].content.controls[0].content.controls
        assert not content[-1].content.controls[0].controls[1].visible
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
