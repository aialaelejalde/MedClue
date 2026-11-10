"""Show saved medications, search, sorting, and the empty cabinet."""

import sqlite3
from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.medications import Medication
from medclue_mobile.ui.components import medication_name, medication_photo, soft_card, use_chips
from medclue_mobile.ui.theme import (CARD_SPACING, CONTENT_PADDING, SCREEN_MARGIN)


class HomeScreen(ft.Container):
    def __init__(
        self,
        cabinet: MedicationCabinet,
        on_open_medication: Callable[[int], Awaitable[None]],
        on_identify: Callable[[], Awaitable[None]],
        on_add: Callable[[], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
        self._cabinet = cabinet
        self._on_open_medication = on_open_medication
        self._on_identify = on_identify
        self._on_add = on_add

        self.search_field = ft.TextField(
            hint_text="Search name or use...",
            value="",
            prefix_icon=ft.Icons.SEARCH,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=16),
            on_change=self._filters_changed,
        )
        self.sort_dropdown = ft.Dropdown(
            expand=True,
            expanded_insets=ft.Padding.all(0),
            label="Sort by",
            value="recently_added",
            options=[
                ft.DropdownOption(key="recently_added", text="Recently added"),
                ft.DropdownOption(key="name_az", text="Name A-Z"),
            ],
            on_select=self._filters_changed,
        )
        self._medication_list = ft.ListView(expand=True, spacing=CARD_SPACING)
        self._no_results = ft.Column(
            controls=[
                ft.Container(
                    content=ft.Text("No medications found", theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
                    expand=True,
                ),
                ft.OutlinedButton("Clear search", on_click=self._clear_search),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
            visible=False,
        )
        self._empty_state = ft.Column(
            controls=[
                ft.Container(
                    content=ft.Text(
                        "Your medicine cabinet is empty",
                        theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                ),
                ft.Column(
                    controls=[
                        ft.FilledButton("Identify medication", on_click=self._identify),
                        ft.OutlinedButton("Add medication manually", on_click=self._add),
                    ],
                    spacing=6,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    tight=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
            visible=False,
        )
        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.Text("My medications", theme_style=ft.TextThemeStyle.HEADLINE_LARGE),
                    self.search_field,
                    ft.Row(controls=[self.sort_dropdown]),
                    self._medication_list,
                    self._empty_state,
                    self._no_results,
                ],
                spacing=CARD_SPACING,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )
        self.refresh()

    def refresh(self) -> None:
        """Reload saved records while keeping the current search and sort order."""
        query = self.search_field.value or ""
        self._empty_state.visible = False
        self._no_results.visible = False
        self._medication_list.visible = True
        try:
            medications = self._cabinet.list_medications(query, self.sort_dropdown.value)
        except (sqlite3.Error, OSError, ValueError):
            controls = [
                ft.Text("Cannot load medications", theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
                ft.Text("We couldn't load your medicine cabinet. Please try again."),
                ft.TextButton("Try again", on_click=self._filters_changed),
            ]
        else:
            if medications:
                controls = [self._medication_card(medication) for medication in medications]
            elif query.strip():
                controls = []
                self._medication_list.visible = False
                self._no_results.visible = True
            else:
                controls = []
                self._empty_state.visible = True
                self._medication_list.visible = False

        self._medication_list.controls = controls
        if self.parent is not None:
            self.update()

    def _medication_card(self, medication: Medication) -> ft.Container:
        async def open_medication(event: ft.Event) -> None:
            await self._on_open_medication(medication.id)

        photo = medication_photo(None, height=96, width=96)
        photo.height = None
        if medication.photo:
            photo.content = None
            photo.image = ft.DecorationImage(src=medication.photo, fit=ft.BoxFit.COVER)

        details = [medication_name(medication.name)]
        details[0].max_lines = 2
        details[0].overflow = ft.TextOverflow.ELLIPSIS
        if medication.uses:
            details.append(use_chips(medication.uses, compact=True))

        return soft_card(
            ft.Row(
                controls=[
                    photo,
                    ft.Container(
                        content=ft.Column(
                            controls=details, spacing=6, tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        padding=CONTENT_PADDING,
                        expand=True,
                    ),
                ],
                spacing=0,
                height=144,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            on_click=open_medication,
            padding=0,
        )

    def _filters_changed(self, event: ft.Event) -> None:
        self.refresh()

    def _clear_search(self, event: ft.Event) -> None:
        self.search_field.value = ""
        self.refresh()

    async def _identify(self, event: ft.Event) -> None:
        await self._on_identify()

    async def _add(self, event: ft.Event) -> None:
        await self._on_add()
