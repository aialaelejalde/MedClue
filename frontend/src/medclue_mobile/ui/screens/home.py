"""Show saved medications, search, sorting, and the empty cabinet."""

import sqlite3
from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.medications import Medication
from medclue_mobile.ui.components import action_button, medication_name, medication_photo, medication_subtitle, soft_card, use_chips
from medclue_mobile.ui.dialogs import delete_medication_with_confirmation
from medclue_mobile.ui.theme import CARD_SPACING, CONTENT_PADDING, SCREEN_MARGIN, CARD_COLOR, PRIMARY_COLOR, BLUE_SURFACE, DANGER_COLOR


class HomeScreen(ft.Container):
    def __init__(
        self,
        cabinet: MedicationCabinet,
        on_open_medication: Callable[[int], Awaitable[None]],
        on_identify: Callable[[], Awaitable[None]],
        on_add: Callable[[], Awaitable[None]],
        on_edit: Callable[[int], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=SCREEN_MARGIN)
        self._cabinet = cabinet
        self._on_open_medication = on_open_medication
        self._on_identify = on_identify
        self._on_add = on_add
        self._on_edit = on_edit
        self._busy = False

        self.search_field = ft.TextField(
            border=ft.OutlineInputBorder(border_radius=28, side=ft.BorderSide(0, ft.Colors.TRANSPARENT)),
            filled=True, fill_color=CARD_COLOR,
            hint_style=ft.TextStyle(color=PRIMARY_COLOR, size=14),
            hint_text="Search name or use...",
            value="",
            prefix_icon=ft.Icons.SEARCH,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=16),
            on_change=self._filters_changed,
        )
        self.sort_dropdown = ft.Dropdown(
            border=ft.OutlineInputBorder(border_radius=24, side=ft.BorderSide(0, ft.Colors.TRANSPARENT)),
            filled=True, fill_color=CARD_COLOR, dense=True, text_size=12,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            width=174,
            expanded_insets=ft.Padding.all(0),
            value="recently_added",
            options=[
                ft.DropdownOption(key="recently_added", text="Recently added"),
                ft.DropdownOption(key="name_az", text="Name A-Z"),
            ],
            on_select=self._filters_changed,
            menu_style=ft.MenuStyle(bgcolor={ft.ControlState.DEFAULT: CARD_COLOR, ft.ControlState.FOCUSED: BLUE_SURFACE}),
        )
        self._count = ft.Text("0 medications", size=12, color=PRIMARY_COLOR)
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
        self._empty_state = soft_card(ft.Column(
            controls=[
                ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=56, color=PRIMARY_COLOR),
                medication_name("Your cabinet is empty", text_align=ft.TextAlign.CENTER),
                ft.Text("No medications saved yet. Add your first medication or identify one to get started.",
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM, text_align=ft.TextAlign.CENTER),
                ft.Row([action_button("Add medication", self._add, icon=ft.Icons.ADD_CIRCLE_OUTLINE)]),
                ft.Row([action_button("Identify medication", self._identify, icon=ft.Icons.CAMERA_ALT_OUTLINED, kind="secondary")]),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=CONTENT_PADDING, scroll=ft.ScrollMode.AUTO, expand=True,
        ))
        self._empty_state.expand = True
        self._empty_state.visible = False
        self.content = ft.SafeArea(
            content=ft.Column(
                controls=[
                    ft.Container(content=self.search_field, border_radius=28,
                                 shadow=ft.BoxShadow(color=ft.Colors.with_opacity(0.04, PRIMARY_COLOR), blur_radius=4, offset=ft.Offset(0, 2))),
                    ft.Row(controls=[self.sort_dropdown, self._count], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
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
            total = len(self._cabinet.list_medications()) if query.strip() else len(medications)
            self._count.value = f"{total} medications"
            for option in self.sort_dropdown.options:
                option.style = ft.ButtonStyle(
                    bgcolor=BLUE_SURFACE if option.key == self.sort_dropdown.value else CARD_COLOR,
                    color=PRIMARY_COLOR,
                )
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

        async def edit_medication(event: ft.Event) -> None:
            await self._on_edit(medication.id)

        async def delete_medication(event: ft.Event) -> None:
            if self._busy:
                return
            self._busy = True
            try:
                if await delete_medication_with_confirmation(self.page, lambda: self._cabinet.delete_medication(medication.id)):
                    self.refresh()
            finally:
                self._busy = False

        photo = medication_photo(medication.photo, height=96, width=80, fit=ft.BoxFit.COVER)
        name = medication_name(medication.name, max_lines=2)
        details = [name, medication_subtitle(medication.strength, medication.form)]
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
                        expand=True,
                    ),
                    ft.Container(content=ft.PopupMenuButton(
                        icon=ft.Icons.MORE_VERT, tooltip="Medication actions",
                        items=[
                            ft.PopupMenuItem(content="Open", on_click=open_medication),
                            ft.PopupMenuItem(content="Edit", on_click=edit_medication),
                            ft.PopupMenuItem(content=ft.Text("Delete", color=DANGER_COLOR), on_click=delete_medication),
                        ],
                    ), alignment=ft.Alignment.TOP_RIGHT, height=96),
                ],
                spacing=CARD_SPACING,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=open_medication,
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
