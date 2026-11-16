"""Set up the app and manage screen navigation."""

import asyncio
import os
import sqlite3
from collections.abc import Awaitable
from pathlib import Path

import flet as ft

from medclue_mobile.api_client import ApiError, MedClueApiClient
from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.identification import IdentificationSession
from medclue_mobile.medications import Medication
from medclue_mobile.photos import PhotoManager
from medclue_mobile.sqlite_repository import MedicationRepository
from medclue_mobile.ui.components import retry_icon
from medclue_mobile.ui.dialogs import confirm_leave_identification, show_error
from medclue_mobile.ui.photo_capture import PhotoCaptureDialog
from medclue_mobile.ui.screens.home import HomeScreen
from medclue_mobile.ui.screens.identification_result import IdentificationResultScreen
from medclue_mobile.ui.screens.identify import IdentifyScreen
from medclue_mobile.ui.screens.identifying_medication import IdentifyingMedicationScreen
from medclue_mobile.ui.screens.medication_details import MedicationDetailsScreen
from medclue_mobile.ui.screens.medication_editor import MedicationEditorScreen
from medclue_mobile.ui.screens.possible_match_result import PossibleMatchResultScreen
from medclue_mobile.ui.screens.possible_matches import PossibleMatchesScreen
from medclue_mobile.ui.theme import (
    BACKGROUND_COLOR,
    BAR_HEIGHT,
    CARD_COLOR,
    FONT_FAMILY,
    HEADER_HEIGHT,
    PRIMARY_COLOR,
    create_theme,
)


DEFAULT_BACKEND_URL = "https://medclue-api-377942439711.europe-southwest1.run.app"
HOME_TAB = 0
IDENTIFY_TAB = 1
ADD_TAB = 2
LOGO_WIDTH = 116
LOGO_HEIGHT = 24
HEADER_TITLE_SPACING = 16


class MedClueApp:
    def __init__(self, page: ft.Page, backend_url: str | None = None, *, database_path: Path | None = None):
        self._page = page
        self._backend_url = (backend_url if backend_url is not None else os.getenv("MEDCLUE_BACKEND_URL", DEFAULT_BACKEND_URL)).strip()
        self._database_path = database_path
        self._cabinet: MedicationCabinet | None = None
        self._api_client: MedClueApiClient | None = None
        self._session: IdentificationSession | None = None
        self._screen: ft.Control | None = None
        self._medication_id: int | None = None
        self._tab = HOME_TAB
        self._navigating = False
        self._attempt_id = 0
        self._closed = False
        self._photo_dialog: PhotoCaptureDialog | None = None
        self._navigation = ft.NavigationBar(
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icon(ft.Icons.HOME_OUTLINED, color=PRIMARY_COLOR), selected_icon=ft.Icon(ft.Icons.HOME, color=PRIMARY_COLOR), label="Home"),
                ft.NavigationBarDestination(icon=ft.Icon(ft.Icons.CAMERA_ALT_OUTLINED, color=PRIMARY_COLOR), selected_icon=ft.Icon(ft.Icons.CAMERA_ALT, color=PRIMARY_COLOR), label="Identify"),
                ft.NavigationBarDestination(icon=ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, color=PRIMARY_COLOR), selected_icon=ft.Icon(ft.Icons.ADD_CIRCLE, color=PRIMARY_COLOR), label="Add"),
            ],
            selected_index=HOME_TAB,
            on_change=self._tab_changed,
            height=BAR_HEIGHT,
            bgcolor=CARD_COLOR,
            indicator_color=ft.Colors.TRANSPARENT,
        )
        self._view = page.views[0] if page.views else ft.View()
        self._view.padding = 0
        self._view.spacing = 0
        self._view.bgcolor = BACKGROUND_COLOR
        self._view.on_confirm_pop = self._back
        self._view.appbar = ft.AppBar(
            title=ft.Image(src="medclue_logo.png", width=LOGO_WIDTH, height=LOGO_HEIGHT,
                           fit=ft.BoxFit.CONTAIN, semantics_label="MedClue"),
            automatically_imply_leading=False, center_title=False,
            toolbar_height=HEADER_HEIGHT, bgcolor=CARD_COLOR, elevation=0, elevation_on_scroll=0,
            title_spacing=HEADER_TITLE_SPACING,
        )

    async def start(self) -> None:
        self._page.title = "MedClue"
        self._page.fonts = {FONT_FAMILY: "fonts/PlusJakartaSans.ttf"}
        self._page.theme = create_theme()
        self._page.bgcolor = BACKGROUND_COLOR
        self._page.theme_mode = ft.ThemeMode.LIGHT
        self._page.locale_configuration = ft.LocaleConfiguration(supported_locales=[ft.Locale("en", "GB")])
        self._page.on_disconnect = self.close
        self._page.on_close = self.close
        self._page.on_app_lifecycle_state_change = self._lifecycle_changed
        self._view.controls = []
        if not self._page.views:
            self._page.views.append(self._view)
        while not self._closed:
            try:
                if self._database_path is None:
                    storage = os.getenv("FLET_APP_STORAGE_DATA")
                    if not storage:
                        storage = await ft.StoragePaths().get_application_documents_directory()
                    self._database_path = Path(storage) / "medclue.db"
                self._database_path.parent.mkdir(parents=True, exist_ok=True)
                repository = MedicationRepository(self._database_path)
                repository.initialize()
                self._cabinet = MedicationCabinet(repository)
                break
            except (OSError, sqlite3.Error, ValueError, ft.FletException):
                if self._closed or not await show_error(
                    self._page, "Cannot open medicine cabinet",
                    "We couldn't open your saved medications. Please try again.",
                    action_text="Try again", action_icon=retry_icon(),
                ):
                    return
        if not self._closed:
            self._show_home()

    async def close(self, event: ft.Event | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        self._reset_identification()
        if self._photo_dialog is not None:
            self._photo_dialog.close()
        if self._api_client is not None:
            await self._api_client.close()

    def _show_screen(self, screen: ft.Control, tab: int) -> None:
        if self._closed:
            return
        self._screen = screen
        self._tab = tab
        self._navigation.selected_index = tab
        self._view.navigation_bar = self._navigation
        self._view.floating_action_button = None
        self._view.can_pop = isinstance(screen, HomeScreen)
        self._view.controls = [screen]
        self._page.update()

    def _show_home(self) -> None:
        self._medication_id = None
        self._show_screen(HomeScreen(self._cabinet, self._open_details, self._open_identify, self._open_add, self._open_edit), HOME_TAB)

    async def _open_details(self, medication_id: int) -> None:
        try:
            medication = self._cabinet.get_medication(medication_id)
        except (sqlite3.Error, OSError, ValueError, LookupError):
            await show_error(self._page, "Cannot open medication", "We couldn't load this medication. Please try again.")
            return
        self._medication_id = medication_id
        self._show_screen(MedicationDetailsScreen(self._cabinet, medication, self._open_edit, self._after_deleted), HOME_TAB)

    async def _open_edit(self, medication_id: int) -> None:
        try:
            medication = self._cabinet.get_medication(medication_id)
        except (sqlite3.Error, OSError, ValueError, LookupError):
            await show_error(self._page, "Cannot edit medication", "We couldn't load this medication. Please try again.")
            return
        self._medication_id = medication_id
        self._show_screen(MedicationEditorScreen(
            self._cabinet, self._after_saved, mode="edit", medication=medication,
            on_take_photo=self._take_photo,
        ), HOME_TAB)

    async def _open_add(self, medication: Medication | None = None, official_uses: list[str] | None = None) -> None:
        suggested_name = bool(medication and medication.name and official_uses is None)
        screen = MedicationEditorScreen(
            self._cabinet, self._after_saved, mode="add", medication=medication, official_uses=official_uses,
            suggested_name=suggested_name, on_take_photo=self._take_photo,
        )
        self._reset_identification()
        self._show_screen(screen, ADD_TAB)

    async def _after_saved(self, medication: Medication) -> None:
        self._medication_id = medication.id
        self._show_screen(MedicationDetailsScreen(self._cabinet, medication, self._open_edit, self._after_deleted), HOME_TAB)

    async def _after_deleted(self) -> None:
        self._show_home()

    async def _open_identify(self) -> None:
        if self._session is None:
            try:
                if not self._backend_url:
                    raise ValueError("The backend URL has not been configured.")
                self._api_client = MedClueApiClient(self._backend_url)
                self._session = IdentificationSession(self._api_client)
            except ValueError:
                await show_error(
                    self._page, "Identification unavailable",
                    "Identification isn't available right now. You can add medication manually.",
                )
                return
        self._reset_identification()
        self._show_screen(IdentifyScreen(PhotoManager(), self._identify), IDENTIFY_TAB)

    def _reset_identification(self) -> None:
        self._attempt_id += 1
        if self._session is not None:
            self._session.cancel()

    async def _identify(self, photo: bytes, media_type: str) -> None:
        await self._run_identification(self._session.identify(photo, media_type))

    async def _select_match(self, index: int) -> None:
        await self._run_identification(self._session.select_match(index))

    async def _retry_identification(self) -> None:
        await self._run_identification(self._session.retry())

    async def _run_identification(self, operation: Awaitable[dict]) -> None:
        self._attempt_id += 1
        attempt_id = self._attempt_id
        self._show_screen(IdentifyingMedicationScreen(self._open_identify), IDENTIFY_TAB)
        try:
            result = await operation
            if self._closed or attempt_id != self._attempt_id:
                return
            photo = self._session.photo
            if result["status"] == "verified":
                screen = IdentificationResultScreen(
                    result, photo, self._open_add, self._open_identify,
                    on_retry=self._retry_identification,
                )
            elif result["status"] == "multiple_matches":
                screen = PossibleMatchesScreen(result, photo, self._select_match, self._open_identify, self._open_add)
            else:
                screen = PossibleMatchResultScreen(result, photo, self._retry_identification, self._open_identify, self._open_add)
            self._show_screen(screen, IDENTIFY_TAB)
        except asyncio.CancelledError:
            return
        except (ApiError, ValueError, LookupError):
            if not self._closed and attempt_id == self._attempt_id:
                await show_error(
                    self._page, "Identification unavailable",
                    "We couldn't complete identification. Please take another photo.",
                )
                if not self._closed and attempt_id == self._attempt_id:
                    await self._open_identify()

    async def _can_leave(self) -> bool:
        if self._photo_dialog is not None:
            return False
        if isinstance(self._screen, MedicationEditorScreen):
            return await self._screen.can_leave()
        if isinstance(self._screen, IdentifyingMedicationScreen):
            return await confirm_leave_identification(self._page)
        return True

    async def _tab_changed(self, event: ft.Event) -> None:
        if self._closed:
            return
        selected = event.control.selected_index
        self._navigation.selected_index = self._tab
        self._page.update()
        if self._closed or self._navigating or self._screen is None:
            return
        if selected == self._tab and (
            isinstance(self._screen, (HomeScreen, IdentifyScreen))
            or (isinstance(self._screen, MedicationEditorScreen) and not self._screen.is_editing)
        ):
            return
        self._navigating = True
        try:
            if not await self._can_leave() or self._closed:
                return
            if selected == HOME_TAB:
                self._reset_identification()
                self._show_home()
            elif selected == IDENTIFY_TAB:
                await self._open_identify()
            elif selected == ADD_TAB:
                await self._open_add()
        finally:
            self._navigating = False

    async def _back(self, event: ft.Event) -> None:
        if self._closed:
            return
        await self._view.confirm_pop(False)
        if self._closed or self._navigating or self._photo_dialog is not None:
            return
        self._navigating = True
        try:
            if isinstance(self._screen, MedicationEditorScreen):
                if await self._screen.can_leave() and not self._closed:
                    if self._screen.is_editing:
                        await self._open_details(self._medication_id)
                    else:
                        self._show_home()
            elif isinstance(self._screen, (MedicationDetailsScreen, IdentifyScreen)):
                self._reset_identification()
                self._show_home()
            elif not isinstance(self._screen, HomeScreen):
                await self._open_identify()
        finally:
            self._navigating = False

    async def _take_photo(self) -> bytes | None:
        dialog = PhotoCaptureDialog(self._page)
        self._photo_dialog = dialog
        try:
            return await dialog.open()
        finally:
            self._photo_dialog = None

    async def _lifecycle_changed(self, event: ft.AppLifecycleStateChangeEvent) -> None:
        if event.state == ft.AppLifecycleState.DETACH:
            await self.close()
