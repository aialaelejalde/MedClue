"""Show candidates and let the user select one."""

from collections.abc import Awaitable, Callable
from copy import deepcopy

import flet as ft

from medclue_mobile.medications import Medication
from medclue_mobile.ui.components import MatchOption, action_button, medication_name, result_layout, status_photo
from medclue_mobile.ui.theme import CARD_SPACING, SCREEN_MARGIN


class PossibleMatchesScreen(ft.Container):
    def __init__(
        self,
        result: dict,
        photo: bytes | None,
        on_select: Callable[[int], Awaitable[None]],
        on_retake: Callable[[], Awaitable[None]],
        on_add: Callable[[Medication], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=ft.Padding.symmetric(horizontal=SCREEN_MARGIN))
        if not isinstance(result, dict) or result.get("status") != "multiple_matches":
            raise ValueError("A multiple-matches result is required.")
        candidates = result.get("candidates", [])
        presentations = result.get("presentations", [])
        if not isinstance(candidates, list) or not isinstance(presentations, list):
            raise ValueError("Possible matches must be lists.")
        options = candidates or presentations
        if (candidates and presentations) or len(options) < 2:
            raise ValueError("Provide at least two candidates or CIMA presentations.")
        for option in options:
            if not isinstance(option, dict):
                raise ValueError("Each possible match must contain medication data.")
            name = option.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Each possible match needs a medication name.")
            for field in ("strength", "form"):
                value = option.get(field)
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    raise ValueError("Match details must contain text or null.")
            if presentations:
                national_code = option.get("national_code")
                if not isinstance(national_code, str) or not national_code.strip():
                    raise ValueError("Each CIMA presentation needs a national code.")

        if photo is not None and (not isinstance(photo, bytes) or not photo):
            raise ValueError("The photo must contain image bytes.")
        suggested_candidate = result.get("suggested_candidate")
        suggested_name = None
        if suggested_candidate is not None:
            if candidates or not isinstance(suggested_candidate, dict):
                raise ValueError("Do not select an AI candidate automatically.")
            suggested_name = suggested_candidate.get("name")
            if not isinstance(suggested_name, str) or not suggested_name.strip():
                raise ValueError("The suggested medication name must contain text.")

        self._medication = Medication(name=suggested_name, photo=photo,
                                      strength=suggested_candidate.get("strength") if suggested_candidate else None,
                                      form=suggested_candidate.get("form") if suggested_candidate else None)
        self._on_select = on_select
        self._on_retake = on_retake
        self._on_add = on_add
        self._busy = False
        self._match_list = ft.Column(
            controls=[self._match_card(index, option) for index, option in enumerate(options)],
            spacing=CARD_SPACING,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._retake_button = action_button("Retake photo", self._retake_photo, icon=ft.Icons.CAMERA_ALT_OUTLINED, kind="secondary")
        self._add_button = action_button("Add medication manually", self._add, icon=ft.Icons.ADD_CIRCLE_OUTLINE, kind="tertiary")
        self.content = result_layout([
            status_photo(photo, "possible", "Possible matches"),
            medication_name("Possible matches", theme_style=ft.TextThemeStyle.TITLE_LARGE),
            ft.Text("Select the medication that matches your item", theme_style=ft.TextThemeStyle.BODY_MEDIUM),
            self._match_list,
        ], [self._retake_button, self._add_button])

    def _match_card(self, index: int, option: dict) -> MatchOption:
        async def select(event: ft.Event) -> None:
            if self._busy:
                return
            card.set_selected(True)
            self._set_busy(True)
            try:
                await self._on_select(index)
            finally:
                self._set_busy(False)

        card = MatchOption(option["name"], option.get("strength"), option.get("form"), on_click=select)
        return card

    async def _retake_photo(self, event: ft.Event) -> None:
        if self._busy:
            return
        self._set_busy(True)
        try:
            await self._on_retake()
        finally:
            self._set_busy(False)

    async def _add(self, event: ft.Event) -> None:
        if self._busy:
            return
        self._set_busy(True)
        try:
            await self._on_add(deepcopy(self._medication))
        finally:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._match_list.disabled = busy
        for card in self._match_list.controls:
            card.disabled = busy
        self._retake_button.disabled = busy
        self._add_button.disabled = busy
        if self.parent is not None:
            self.update()
