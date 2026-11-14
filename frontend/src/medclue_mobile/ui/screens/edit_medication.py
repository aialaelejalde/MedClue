"""Edit a saved medication."""

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import replace

import flet as ft

from medclue_mobile.cabinet import DuplicateMedicationError, MedicationCabinet
from medclue_mobile.medications import Medication, validate_medication
from medclue_mobile.photos import CameraPermissionError, compress_photo
from medclue_mobile.ui.components import action_button
from medclue_mobile.ui.dialogs import (confirm_discard_changes, confirm_duplicate, show_error, show_save_success)
from medclue_mobile.ui.medication_form import MedicationForm, form_screen_layout
from medclue_mobile.ui.theme import SCREEN_MARGIN


class EditMedicationScreen(ft.Container):
    def __init__(
        self,
        cabinet: MedicationCabinet,
        medication: Medication,
        on_saved: Callable[[Medication], Awaitable[None]],
        *,
        on_take_photo: Callable[[], Awaitable[bytes | None]] | None = None,
    ):
        super().__init__(expand=True, padding=ft.Padding.symmetric(horizontal=SCREEN_MARGIN))
        validate_medication(medication)
        if medication.id is None:
            raise ValueError("Editing a medication requires a saved record.")

        self._cabinet = cabinet
        self._on_saved = on_saved
        self._on_take_photo = on_take_photo
        self._original_photo = medication.photo
        self._busy = False
        self._saved_medication: Medication | None = None
        self.form = MedicationForm(
            medication,
            on_take_photo=self._take_photo if on_take_photo is not None else None,
        )
        self._save_button = action_button("Save medication", self._save)
        self.content = form_screen_layout(None, self.form, self._save_button)

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
                if draft.photo is not None and draft.photo != self._original_photo:
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
                except (sqlite3.Error, OSError, ValueError, LookupError):
                    retry = await show_error(
                        self.page,
                        "Cannot save medication",
                        "We couldn't save your changes. Please try again.",
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
                "You can edit the medication without changing its photo.",
            )
        except (OSError, ValueError, RuntimeError):
            await show_error(self.page, "Could not take photo", "Please try again.")
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        disabled = busy or self._saved_medication is not None
        self.form.disabled = disabled
        self._save_button.disabled = disabled
        if self.parent is not None:
            self.page.update(self, self._save_button)
