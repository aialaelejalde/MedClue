"""Show saved medications, search, sorting, and the empty cabinet."""

import sqlite3
from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.medications import Medication
from medclue_mobile.ui.components import action_button, medication_name, medication_photo, medication_subtitle, retry_icon, soft_card, stretch_card, text_field, use_chips
from medclue_mobile.ui.dialogs import delete_medication_with_confirmation
from medclue_mobile.ui.theme import CARD_SPACING, CONTENT_PADDING, SCREEN_MARGIN, CARD_COLOR, PRIMARY_COLOR, BLUE_SURFACE, DANGER_COLOR, FONT_FAMILY, TEXT_COLOR


class HomeScreen(ft.Container):
    def __init__(
        self,
        cabinet: MedicationCabinet,
        on_open_medication: Callable[[int], Awaitable[None]],
        on_identify: Callable[[], Awaitable[None]],
        on_add: Callable[[], Awaitable[None]],
        on_edit: Callable[[int], Awaitable[None]],
    ):
        super().__init__(expand=True, padding=ft.Padding.symmetric(horizontal=SCREEN_MARGIN))
        self._cabinet = cabinet
        self._on_open_medication = on_open_medication
        self._on_identify = on_identify
        self._on_add = on_add
        self._on_edit = on_edit
        self._busy = False

        self.search_field = text_field(
            border=ft.OutlineInputBorder(border_radius=28, side=ft.BorderSide(0, ft.Colors.TRANSPARENT)),
            filled=True, fill_color=CARD_COLOR,
            hint_text="Search name or use...",
            value="",
            prefix_icon=ft.Container(content=ft.Icon(ft.Icons.SEARCH, color=PRIMARY_COLOR),
                                     padding=ft.Padding.only(left=8), width=52),
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=16),
            on_change=self._filters_changed,
        )
        self._sort_order = "recently_added"
        self._sort_label = ft.Text("Recently added", size=12, color=TEXT_COLOR, font_family=FONT_FAMILY, expand=True)
        self._sort_button = ft.PopupMenuButton(
            content=ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SWAP_VERT, color=PRIMARY_COLOR, size=20),
                    self._sort_label,
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=PRIMARY_COLOR, size=20),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                bgcolor=CARD_COLOR, border_radius=24,
            ),
            width=212, tooltip="Sort medications",
        )
        self._count = ft.Text("0 medications", size=12, color=PRIMARY_COLOR)
        self._medication_list = ft.Column(tight=True, spacing=CARD_SPACING,
                                          horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self._no_results = ft.Column(
            controls=[
                ft.Container(
                    content=ft.Text("No medications found", theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
                ),
                ft.OutlinedButton("Clear search", on_click=self._clear_search),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            visible=False,
        )
        self._empty_state = soft_card(ft.Column([
            ft.Column(
                controls=[
                    ft.Image(src="empty_cabinet.svg", width=56, height=56, semantics_label="Empty box"),
                    medication_name("Your cabinet is empty", text_align=ft.TextAlign.CENTER),
                    ft.Text("No medications saved yet. Add your first medication or identify one to get started.",
                            theme_style=ft.TextThemeStyle.BODY_MEDIUM, text_align=ft.TextAlign.CENTER),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=CONTENT_PADDING, tight=True,
            ),
            ft.Column([
                ft.Row([action_button("Add medication", self._add, icon=ft.Icons.ADD_CIRCLE_OUTLINE)]),
                ft.Row([action_button("Identify medication", self._identify, icon=ft.Icons.CAMERA_ALT_OUTLINED, kind="secondary")]),
            ], spacing=CONTENT_PADDING, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        ], spacing=CONTENT_PADDING, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH))
        self._empty_state.visible = False
        header = ft.Column(
            controls=[
                ft.Container(content=self.search_field, border_radius=28,
                             shadow=ft.BoxShadow(color=ft.Colors.with_opacity(0.04, PRIMARY_COLOR), blur_radius=4, offset=ft.Offset(0, 2))),
                ft.Row(controls=[
                    self._sort_button, self._count,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ],
            spacing=8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        viewport = ft.ListView(
            controls=[header, self._medication_list, self._empty_state, self._no_results],
            spacing=CONTENT_PADDING, expand=True, padding=ft.Padding.symmetric(vertical=SCREEN_MARGIN),
            on_size_change=stretch_card(self._empty_state, header, leading_spacing=CONTENT_PADDING),
        )
        self.content = ft.SafeArea(content=viewport, avoid_intrusions_top=False, avoid_intrusions_bottom=False)
        self.refresh()

    def refresh(self) -> None:
        """Reload saved records while keeping the current search and sort order."""
        query = self.search_field.value or ""
        self._empty_state.visible = False
        self._no_results.visible = False
        self._medication_list.visible = True
        try:
            medications = self._cabinet.list_medications(query, self._sort_order)
            total = len(self._cabinet.list_medications()) if query.strip() else len(medications)
            self._count.value = f"{total} medication{'s' if total != 1 else ''}"
            self._sort_button.items = [
                self._sort_item("recently_added", "Recently added"),
                self._sort_item("name_az", "Name A-Z"),
            ]
        except (sqlite3.Error, OSError, ValueError):
            controls = [
                ft.Text("Cannot load medications", theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
                ft.Text("We couldn't load your medicine cabinet. Please try again."),
                ft.TextButton("Try again", icon=retry_icon(), on_click=self._filters_changed),
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
        details = [name, medication_subtitle(medication.strength, medication.form, max_lines=2)]
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
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        expand=True,
                    ),
                    ft.Container(content=ft.PopupMenuButton(
                        content=ft.Container(
                            content=ft.Icon(ft.Icons.MORE_VERT, size=24, color=PRIMARY_COLOR),
                            width=56, height=56, alignment=ft.Alignment.TOP_RIGHT,
                            bgcolor=ft.Colors.TRANSPARENT,
                        ),
                        tooltip="Medication actions",
                        padding=0, width=56, height=56,
                        items=[
                            ft.PopupMenuItem(content=ft.Text("Open", color=PRIMARY_COLOR), on_click=open_medication),
                            ft.PopupMenuItem(content=ft.Text("Edit", color=PRIMARY_COLOR), on_click=edit_medication),
                            ft.PopupMenuItem(content=ft.Text("Delete", color=DANGER_COLOR), on_click=delete_medication),
                        ],
                    ), alignment=ft.Alignment.TOP_RIGHT, width=56, height=56),
                ],
                spacing=CARD_SPACING,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            on_click=open_medication,
        )

    def _sort_item(self, order: str, label: str) -> ft.PopupMenuItem:
        def select(event: ft.Event) -> None:
            self._sort_order = order
            self._sort_label.value = label
            self.refresh()

        return ft.PopupMenuItem(
            content=ft.Container(
                content=ft.Row([
                    ft.Text(label, size=12, color=PRIMARY_COLOR, font_family=FONT_FAMILY, expand=True),
                ]),
                bgcolor=BLUE_SURFACE if order == self._sort_order else CARD_COLOR,
                padding=ft.Padding.symmetric(horizontal=12, vertical=16), border_radius=8,
            ),
            padding=ft.Padding.symmetric(horizontal=CONTENT_PADDING),
            on_click=select,
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
