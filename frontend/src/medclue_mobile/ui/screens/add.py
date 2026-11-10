"""Show the form for adding a medication by hand or from a result."""

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import replace

import flet as ft

from medclue_mobile.cabinet import DuplicateMedicationError, MedicationCabinet
from medclue_mobile.medications import Medication
from medclue_mobile.photos import CameraPermissionError, compress_photo
from medclue_mobile.ui.dialogs import (confirm_discard_changes, confirm_duplicate, show_error, show_save_success)
from medclue_mobile.ui.medication_form import MedicationForm
from medclue_mobile.ui.theme import CARD_SPACING, SCREEN_MARGIN


class AddMedicationScreen(ft.Container):
    def __init__(
        self,
        cabinet: MedicationCabinet,
        on_saved: Callable[[Medication], Awaitable[None]],
        *,
        medication: Medication | None = None,
        official_uses: list[str] | None = None,
        suggested_name: bool = False,
        on_take_photo: Callable[[], Awaitable[bytes | None]] | None = None,
    ):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
        if medication is not None and (medication.id is not None or medication.created_at is not None):
            raise ValueError("Adding a medication requires a new record without saved metadata.")

        self._cabinet = cabinet
        self._on_saved = on_saved
        self._on_take_photo = on_take_photo
        self._busy = False
        self._saved_medication: Medication | None = None
        self.form = MedicationForm(
            medication,
            official_uses=official_uses,
            suggested_name=suggested_name,
            on_take_photo=self._take_photo if on_take_photo is not None else None,
        )
        self._save_button = ft.FilledButton("Save medication", on_click=self._save, expand=True)
        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.Text("Add medication", theme_style=ft.TextThemeStyle.HEADLINE_LARGE),
                    self.form,
                    ft.Row(controls=[self._save_button]),
                ],
                spacing=CARD_SPACING,
                expand=True,
            )
        )

    async def can_leave(self) -> bool:
        if self._saved_medication is not None:
            return True
        if self._busy:
            return False
        if not self.form.has_changes():
            return True
        return await confirm_discard_changes(self.page)

    async def _save(self, event: ft.Event) -> None:
        if self._busy or self._saved_medication is not None:
            return
        self._set_busy(True)
        try:
            try:
                draft = self.form.get_medication()
                if draft.photo is not None:
                    photo = await asyncio.to_thread(compress_photo, draft.photo)
                    draft = replace(draft, photo=photo)
            except ValueError as error:
                await show_error(self.page, "Cannot save medication", str(error))
                return

            allow_duplicate = False
            while True:
                try:
                    saved = self._cabinet.save_medication(draft, allow_duplicate=allow_duplicate)
                    break
                except DuplicateMedicationError:
                    if not await confirm_duplicate(self.page):
                        return
                    allow_duplicate = True
                except (sqlite3.Error, OSError, ValueError):
                    retry = await show_error(
                        self.page,
                        "Cannot save medication",
                        "We couldn't save this medication. Please try again.",
                        action_text="Try again",
                    )
                    if not retry:
                        return

            self._saved_medication = saved
            show_save_success(self.page)
            await self._on_saved(saved)
        finally:
            self._set_busy(False)

    async def _take_photo(self, event: ft.Event) -> None:
        if self._busy or self._saved_medication is not None or self._on_take_photo is None:
            return
        self._set_busy(True)
        try:
            photo = await self._on_take_photo()
            if photo is not None:
                self.form.set_photo(photo)
        except CameraPermissionError:
            await show_error(
                self.page,
                "Camera access is off",
                "You can add the medication without a photo.",
            )
        except (OSError, ValueError, RuntimeError):
            await show_error(
                self.page,
                "Could not take photo",
                "Please try again.",
            )
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.form.disabled = busy
        self._save_button.disabled = busy or self._saved_medication is not None
        if self.parent is not None:
            self.update()
