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
from medclue_mobile.photos import CameraPermissionError, PhotoManager
from medclue_mobile.sqlite_repository import MedicationRepository
from medclue_mobile.ui.dialogs import confirm_leave_identification, show_error
from medclue_mobile.ui.screens.add import AddMedicationScreen
from medclue_mobile.ui.screens.edit_medication import EditMedicationScreen
from medclue_mobile.ui.screens.home import HomeScreen
from medclue_mobile.ui.screens.identification_result import IdentificationResultScreen
from medclue_mobile.ui.screens.identify import IdentifyScreen
from medclue_mobile.ui.screens.identifying_medication import IdentifyingMedicationScreen
from medclue_mobile.ui.screens.medication_details import MedicationDetailsScreen
from medclue_mobile.ui.screens.possible_match_result import PossibleMatchResultScreen
from medclue_mobile.ui.screens.possible_matches import PossibleMatchesScreen
from medclue_mobile.ui.theme import BACKGROUND_COLOR, CARD_SPACING, create_theme


SPLASH_DURATION_SECONDS = 3
SPLASH_LOGO_WIDTH = 288


class MedClueApp:
    def __init__(self, page: ft.Page, backend_url: str | None = None, *, database_path: Path | None = None):
        self._page = page
        self._backend_url = (backend_url if backend_url is not None else os.getenv("MEDCLUE_BACKEND_URL", "")).strip()
        self._database_path = database_path
        self._cabinet: MedicationCabinet | None = None
        self._api_client: MedClueApiClient | None = None
        self._session: IdentificationSession | None = None
        self._screen: ft.Control | None = None
        self._medication_id: int | None = None
        self._tab = 0
        self._navigating = False
        self._attempt_id = 0
        self._closed = False
        self._photo_result: asyncio.Future | None = None
        self._navigation = ft.NavigationBar(
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, label="Home"),
                ft.NavigationBarDestination(icon=ft.Icons.CAMERA_ALT_OUTLINED, label="Identify"),
                ft.NavigationBarDestination(icon=ft.Icons.ADD, label="Add"),
            ],
            selected_index=0,
            on_change=self._tab_changed,
        )
        self._view = page.views[0] if page.views else ft.View()
        self._view.padding = 0
        self._view.bgcolor = BACKGROUND_COLOR
        self._view.on_confirm_pop = self._back

    async def start(self) -> None:
        self._page.title = "MedClue"
        self._page.theme = create_theme()
        self._page.bgcolor = BACKGROUND_COLOR
        self._page.theme_mode = ft.ThemeMode.LIGHT
        self._page.locale_configuration = ft.LocaleConfiguration(supported_locales=[ft.Locale("en", "GB")])
        self._page.on_disconnect = self.close
        self._page.on_close = self.close
        self._page.on_app_lifecycle_state_change = self._lifecycle_changed
        self._view.controls = [
            ft.Container(
                content=ft.Image(src="medclue_logo.png", width=SPLASH_LOGO_WIDTH, fit=ft.BoxFit.CONTAIN, semantics_label="MedClue"),
                alignment=ft.Alignment.CENTER,
                padding=24,
                expand=True,
            )
        ]
        if not self._page.views:
            self._page.views.append(self._view)
        self._page.update()
        await asyncio.sleep(SPLASH_DURATION_SECONDS)
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
                    "We couldn't open your saved medications. Please try again.", action_text="Try again",
                ):
                    return
        if not self._closed:
            self._show_home()

    def _show_screen(self, screen: ft.Control, tab: int) -> None:
        if self._closed:
            return
        self._screen = screen
        self._tab = tab
        self._navigation.selected_index = tab
        self._view.navigation_bar = self._navigation
        if isinstance(screen, MedicationDetailsScreen):
            self._view.floating_action_button = screen._edit_button
        elif isinstance(screen, EditMedicationScreen):
            self._view.floating_action_button = screen._save_button
        else:
            self._view.floating_action_button = None
        self._view.floating_action_button_location = ft.FloatingActionButtonLocation.END_FLOAT
        self._view.can_pop = isinstance(screen, HomeScreen)
        self._view.controls = [screen]
        self._page.update()

    def _show_home(self) -> None:
        self._medication_id = None
        self._show_screen(HomeScreen(self._cabinet, self._open_details, self._open_identify, self._open_add), 0)

    async def _open_details(self, medication_id: int) -> None:
        try:
            medication = self._cabinet.get_medication(medication_id)
        except (sqlite3.Error, OSError, ValueError, LookupError):
            await show_error(self._page, "Cannot open medication", "We couldn't load this medication. Please try again.")
            return
        self._medication_id = medication_id
        self._show_screen(MedicationDetailsScreen(self._cabinet, medication, self._open_edit, self._after_deleted), 0)

    async def _open_edit(self, medication_id: int) -> None:
        try:
            medication = self._cabinet.get_medication(medication_id)
        except (sqlite3.Error, OSError, ValueError, LookupError):
            await show_error(self._page, "Cannot edit medication", "We couldn't load this medication. Please try again.")
            return
        self._medication_id = medication_id
        self._show_screen(EditMedicationScreen(self._cabinet, medication, self._after_saved, on_take_photo=self._take_photo), 0)

    async def _open_add(self, medication: Medication | None = None, official_uses: list[str] | None = None) -> None:
        suggested_name = bool(medication and medication.name and official_uses is None)
        screen = AddMedicationScreen(
            self._cabinet, self._after_saved, medication=medication, official_uses=official_uses,
            suggested_name=suggested_name, on_take_photo=self._take_photo,
        )
        self._reset_identification()
        self._show_screen(screen, 2)

    async def _after_saved(self, medication: Medication) -> None:
        self._medication_id = medication.id
        self._show_screen(MedicationDetailsScreen(self._cabinet, medication, self._open_edit, self._after_deleted), 0)

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
        self._show_screen(IdentifyScreen(PhotoManager(), self._identify), 1)

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
        self._show_screen(IdentifyingMedicationScreen(self._open_identify), 1)
        try:
            result = await operation
            if self._closed or attempt_id != self._attempt_id:
                return
            photo = self._session.photo
            if result["status"] == "verified":
                screen = IdentificationResultScreen(result, photo, self._open_add)
            elif result["status"] == "multiple_matches":
                screen = PossibleMatchesScreen(result, photo, self._select_match, self._open_identify, self._open_add)
            else:
                screen = PossibleMatchResultScreen(result, photo, self._retry_identification, self._open_identify, self._open_add)
            self._show_screen(screen, 1)
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
        if self._photo_result is not None:
            return False
        if isinstance(self._screen, (AddMedicationScreen, EditMedicationScreen)):
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
        if selected == self._tab and isinstance(self._screen, (HomeScreen, IdentifyScreen, AddMedicationScreen)):
            return
        self._navigating = True
        try:
            if not await self._can_leave() or self._closed:
                return
            if selected == 0:
                self._reset_identification()
                self._show_home()
            elif selected == 1:
                await self._open_identify()
            elif selected == 2:
                await self._open_add()
        finally:
            self._navigating = False

    async def _back(self, event: ft.Event) -> None:
        if self._closed:
            return
        await self._view.confirm_pop(False)
        if self._closed or self._navigating or self._photo_result is not None:
            return
        self._navigating = True
        try:
            if isinstance(self._screen, EditMedicationScreen):
                if await self._screen.can_leave() and not self._closed:
                    await self._open_details(self._medication_id)
            elif isinstance(self._screen, AddMedicationScreen):
                if await self._screen.can_leave() and not self._closed:
                    self._show_home()
            elif isinstance(self._screen, (MedicationDetailsScreen, IdentifyScreen)):
                self._reset_identification()
                self._show_home()
            elif not isinstance(self._screen, HomeScreen):
                await self._open_identify()
        finally:
            self._navigating = False

    async def _take_photo(self) -> bytes | None:
        photos = PhotoManager()
        result = asyncio.get_running_loop().create_future()
        self._photo_result = result
        capturing = False

        def dismiss(event: ft.Event | None = None) -> None:
            if not result.done():
                result.set_result(None)

        def cancel(event: ft.Event) -> None:
            dismiss()
            if dialog.open:
                self._page.pop_dialog()

        async def capture(event: ft.Event) -> None:
            nonlocal capturing
            if capturing or result.done():
                return
            capturing = True
            take_button.disabled = True
            dialog.update()
            try:
                photo = await photos.capture()
                if not result.done():
                    result.set_result(photo)
                    self._page.pop_dialog()
            except (OSError, ValueError, RuntimeError, ft.FletException):
                if not result.done() and not self._closed:
                    await show_error(self._page, "Could not take photo", "Please try again.")
            finally:
                capturing = False
                take_button.disabled = False
                if dialog.open and not self._closed:
                    dialog.update()

        take_button = ft.FilledButton("Take photo", on_click=capture, disabled=True, expand=True)
        preview_width = 0
        preview_height = 0
        preview_ratio = 3 / 4
        photos.camera.expand = False
        photos.camera.left = 0
        photos.camera.top = 0

        def fit_preview() -> None:
            if result.done() or self._closed or preview_width <= 0 or preview_height <= 0:
                return
            width = max(preview_width, preview_height * preview_ratio)
            height = width / preview_ratio
            photos.camera.width = width
            photos.camera.height = height
            photos.camera.left = (preview_width - width) / 2
            photos.camera.top = (preview_height - height) / 2
            photos.camera.update()

        def resize_preview(event: ft.LayoutSizeChangeEvent) -> None:
            nonlocal preview_width, preview_height
            preview_width, preview_height = event.width, event.height
            fit_preview()

        def camera_changed(event: ft.Event) -> None:
            nonlocal preview_ratio
            ratio = event.aspect_ratio
            if ratio is None or ratio <= 0:
                return
            orientation = event.preview_pause_orientation or event.locked_capture_orientation or event.device_orientation
            landscape = orientation in (ft.DeviceOrientation.LANDSCAPE_LEFT, ft.DeviceOrientation.LANDSCAPE_RIGHT)
            preview_ratio = max(ratio, 1 / ratio) if landscape else min(ratio, 1 / ratio)
            fit_preview()

        photos.camera.on_state_change = camera_changed
        camera_frame = ft.Container(
            content=ft.Stack(controls=[photos.camera]),
            aspect_ratio=4 / 3,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            border_radius=16,
            on_size_change=resize_preview,
        )
        dialog = ft.AlertDialog(
            title=ft.Text("Medication photo"),
            content=ft.Container(
                width=min(420, (self._page.width or 360) - 80),
                content=ft.Column(
                    controls=[
                        camera_frame,
                        ft.Row(controls=[take_button]),
                    ],
                    spacing=CARD_SPACING,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
            actions=[ft.TextButton("Cancel", on_click=cancel)],
            on_dismiss=dismiss,
            scrollable=True,
            bgcolor=BACKGROUND_COLOR,
        )
        self._page.show_dialog(dialog)
        try:
            try:
                await photos.initialize_camera()
            except CameraPermissionError:
                if result.done():
                    return None
                raise
            except (OSError, ValueError, RuntimeError, ft.FletException):
                if result.done():
                    return None
                if not self._closed:
                    await show_error(self._page, "Could not take photo", "We couldn't start the camera. Please try again.")
                return None
            if not result.done() and not self._closed:
                take_button.disabled = False
                dialog.update()
            return await result
        finally:
            photos.discard_photo()
            self._photo_result = None
            if dialog.open and not self._closed:
                self._page.pop_dialog()

    async def _lifecycle_changed(self, event: ft.AppLifecycleStateChangeEvent) -> None:
        if event.state == ft.AppLifecycleState.DETACH:
            await self.close()

    async def close(self, event: ft.Event | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        self._reset_identification()
        if self._photo_result is not None and not self._photo_result.done():
            self._photo_result.set_result(None)
        if self._api_client is not None:
            await self._api_client.close()
