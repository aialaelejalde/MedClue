"""Add or edit a medication using the shared form."""

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Literal

import flet as ft

from medclue_mobile.cabinet import DuplicateMedicationError, MedicationCabinet
from medclue_mobile.medications import Medication, validate_medication
from medclue_mobile.photos import CameraPermissionError, compress_photo
from medclue_mobile.ui.components import action_button, retry_icon
from medclue_mobile.ui.dialogs import (
    confirm_discard_changes,
    confirm_duplicate,
    show_error,
    show_save_success,
)
from medclue_mobile.ui.medication_form import MedicationForm, form_screen_layout
from medclue_mobile.ui.theme import SCREEN_MARGIN


class MedicationEditorScreen(ft.Container):
    def __init__(
        self,
        cabinet: MedicationCabinet,
        on_saved: Callable[[Medication], Awaitable[None]],
        *,
        mode: Literal["add", "edit"],
        medication: Medication | None = None,
        official_uses: list[str] | None = None,
        suggested_name: bool = False,
        on_take_photo: Callable[[], Awaitable[bytes | None]] | None = None,
    ):
        super().__init__(expand=True, padding=ft.Padding.symmetric(horizontal=SCREEN_MARGIN))
        if mode not in ("add", "edit"):
            raise ValueError("The medication editor mode must be add or edit.")
        self._mode = mode
        if self.is_editing:
            validate_medication(medication)
            if medication.id is None:
                raise ValueError("Editing a medication requires a saved record.")
        elif medication is not None and (medication.id is not None or medication.created_at is not None):
            raise ValueError("Adding a medication requires a new record without saved metadata.")

        self._cabinet = cabinet
        self._on_saved = on_saved
        self._on_take_photo = on_take_photo
        self._original_photo = medication.photo if medication is not None else None
        self._busy = False
        self._saved_medication: Medication | None = None
        self.form = MedicationForm(
            medication,
            official_uses=official_uses,
            suggested_name=suggested_name,
            on_take_photo=self._take_photo if on_take_photo is not None else None,
        )
        self._save_button = action_button("Save medication", self._save, icon=ft.Icons.SAVE_OUTLINED)
        self.content = form_screen_layout(self.form, self._save_button)

    @property
    def is_editing(self) -> bool:
        return self._mode == "edit"

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
                if draft.photo is not None and (not self.is_editing or draft.photo != self._original_photo):
                    photo = await asyncio.to_thread(compress_photo, draft.photo)
                    draft = replace(draft, photo=photo)
            except ValueError as error:
                await show_error(self.page, "Cannot save medication", str(error))
                return

            save_errors = (sqlite3.Error, OSError, ValueError)
            if self.is_editing:
                save_errors += (LookupError,)
            allow_duplicate = False
            while True:
                try:
                    saved = self._cabinet.save_medication(draft, allow_duplicate=allow_duplicate)
                    break
                except DuplicateMedicationError:
                    if not await confirm_duplicate(self.page):
                        return
                    allow_duplicate = True
                except save_errors:
                    retry = await show_error(
                        self.page,
                        "Cannot save medication",
                        "We couldn't save your changes. Please try again." if self.is_editing else
                        "We couldn't save this medication. Please try again.",
                        action_text="Try again", action_icon=retry_icon(),
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
                "You can edit the medication without changing its photo." if self.is_editing else
                "You can add the medication without a photo.",
            )
        except (OSError, ValueError, RuntimeError):
            await show_error(self.page, "Could not take photo", "Please try again.")
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.form.disabled = busy or (self.is_editing and self._saved_medication is not None)
        self._save_button.disabled = busy or self._saved_medication is not None
        if self.parent is not None:
            if self.is_editing:
                self.page.update(self, self._save_button)
            else:
                self.update()
