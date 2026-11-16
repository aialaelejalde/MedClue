"""Show saved medications, search, sorting, and the empty cabinet."""

import sqlite3
from collections.abc import Awaitable, Callable

import flet as ft

from medclue_mobile.cabinet import MedicationCabinet
from medclue_mobile.medications import Medication
from medclue_mobile.ui.components import action_button, medication_name, medication_photo, medication_subtitle, retry_icon, soft_card, stretch_card, text_field, use_chips
from medclue_mobile.ui.dialogs import delete_medication_with_confirmation
from medclue_mobile.ui.theme import (
    BLUE_SURFACE,
    CARD_COLOR,
    CARD_SPACING,
    CONTENT_PADDING,
    DANGER_COLOR,
    FONT_FAMILY,
    ICON_SIZE,
    PRIMARY_COLOR,
    SCREEN_MARGIN,
    SMALL_ICON_SIZE,
    TEXT_COLOR,
    TEXT_SIZE_SMALL,
)


SORT_LABELS = {
    "recently_added": "Recently added",
    "name_az": "Name A-Z",
}

SEARCH_FIELD_RADIUS = 28
SEARCH_ICON_LEFT_PADDING = 8
SEARCH_ICON_WIDTH = 52
SEARCH_HORIZONTAL_PADDING = 12
SEARCH_VERTICAL_PADDING = 16
SEARCH_SHADOW_OPACITY = 0.04
SEARCH_SHADOW_BLUR_RADIUS = 4
SEARCH_SHADOW_VERTICAL_OFFSET = 2
HEADER_SPACING = 8

SORT_CONTROL_SPACING = 8
SORT_CONTROL_HORIZONTAL_PADDING = 12
SORT_CONTROL_VERTICAL_PADDING = 8
SORT_CONTROL_RADIUS = 24
SORT_MENU_WIDTH = 212
SORT_OPTION_HORIZONTAL_PADDING = 12
SORT_OPTION_VERTICAL_PADDING = 16
SORT_OPTION_RADIUS = 8

EMPTY_CABINET_ICON_SIZE = 56
MEDICATION_THUMBNAIL_WIDTH = 80
MEDICATION_THUMBNAIL_HEIGHT = 96
MEDICATION_MENU_SIZE = 56
MEDICATION_SUMMARY_MAX_LINES = 2
MEDICATION_DETAILS_SPACING = 6


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
        self._sort_order = "recently_added"

        header = self._build_header()
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
        self._empty_state = self._build_empty_state()
        self._empty_state.visible = False
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
            total = self._cabinet.count_medications() if query.strip() else len(medications)
            self._count.value = f"{total} medication{'s' if total != 1 else ''}"
            self._sort_button.items = [
                self._sort_item(order, label) for order, label in SORT_LABELS.items()
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

    def _build_header(self) -> ft.Column:
        self.search_field = text_field(
            border=ft.OutlineInputBorder(border_radius=SEARCH_FIELD_RADIUS, side=ft.BorderSide(0, ft.Colors.TRANSPARENT)),
            filled=True, fill_color=CARD_COLOR,
            hint_text="Search name or use...",
            value="",
            prefix_icon=ft.Container(content=ft.Icon(ft.Icons.SEARCH, color=PRIMARY_COLOR),
                                     padding=ft.Padding.only(left=SEARCH_ICON_LEFT_PADDING), width=SEARCH_ICON_WIDTH),
            content_padding=ft.Padding.symmetric(horizontal=SEARCH_HORIZONTAL_PADDING, vertical=SEARCH_VERTICAL_PADDING),
            on_change=self._filters_changed,
        )
        self._sort_label = ft.Text(SORT_LABELS[self._sort_order], size=TEXT_SIZE_SMALL, color=TEXT_COLOR, font_family=FONT_FAMILY, expand=True)
        self._sort_button = ft.PopupMenuButton(
            content=ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SWAP_VERT, color=PRIMARY_COLOR, size=SMALL_ICON_SIZE),
                    self._sort_label,
                    ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=PRIMARY_COLOR, size=SMALL_ICON_SIZE),
                ], spacing=SORT_CONTROL_SPACING, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(horizontal=SORT_CONTROL_HORIZONTAL_PADDING, vertical=SORT_CONTROL_VERTICAL_PADDING),
                bgcolor=CARD_COLOR, border_radius=SORT_CONTROL_RADIUS,
            ),
            width=SORT_MENU_WIDTH, tooltip="Sort medications",
        )
        self._count = ft.Text("0 medications", size=TEXT_SIZE_SMALL, color=PRIMARY_COLOR)
        return ft.Column(
            controls=[
                ft.Container(content=self.search_field, border_radius=SEARCH_FIELD_RADIUS,
                             shadow=ft.BoxShadow(color=ft.Colors.with_opacity(SEARCH_SHADOW_OPACITY, PRIMARY_COLOR),
                                                 blur_radius=SEARCH_SHADOW_BLUR_RADIUS,
                                                 offset=ft.Offset(0, SEARCH_SHADOW_VERTICAL_OFFSET))),
                ft.Row(controls=[
                    self._sort_button, self._count,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ],
            spacing=HEADER_SPACING,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def _build_empty_state(self) -> ft.Container:
        return soft_card(ft.Column([
            ft.Column(
                controls=[
                    ft.Image(src="empty_cabinet.svg", width=EMPTY_CABINET_ICON_SIZE,
                             height=EMPTY_CABINET_ICON_SIZE, semantics_label="Empty box"),
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

        photo = medication_photo(medication.photo, height=MEDICATION_THUMBNAIL_HEIGHT, width=MEDICATION_THUMBNAIL_WIDTH, fit=ft.BoxFit.COVER)
        name = medication_name(medication.name, max_lines=MEDICATION_SUMMARY_MAX_LINES)
        details = [name, medication_subtitle(medication.strength, medication.form, max_lines=MEDICATION_SUMMARY_MAX_LINES)]
        if medication.uses:
            details.append(use_chips(medication.uses, compact=True))

        return soft_card(
            ft.Row(
                controls=[
                    photo,
                    ft.Container(
                        content=ft.Column(
                            controls=details, spacing=MEDICATION_DETAILS_SPACING, tight=True,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        expand=True,
                    ),
                    ft.Container(content=ft.PopupMenuButton(
                        content=ft.Container(
                            content=ft.Icon(ft.Icons.MORE_VERT, size=ICON_SIZE, color=PRIMARY_COLOR),
                            width=MEDICATION_MENU_SIZE, height=MEDICATION_MENU_SIZE, alignment=ft.Alignment.TOP_RIGHT,
                            bgcolor=ft.Colors.TRANSPARENT,
                        ),
                        tooltip="Medication actions",
                        padding=0, width=MEDICATION_MENU_SIZE, height=MEDICATION_MENU_SIZE,
                        items=[
                            ft.PopupMenuItem(content=ft.Text("Open", color=PRIMARY_COLOR), on_click=open_medication),
                            ft.PopupMenuItem(content=ft.Text("Edit", color=PRIMARY_COLOR), on_click=edit_medication),
                            ft.PopupMenuItem(content=ft.Text("Delete", color=DANGER_COLOR), on_click=delete_medication),
                        ],
                    ), alignment=ft.Alignment.TOP_RIGHT, width=MEDICATION_MENU_SIZE, height=MEDICATION_MENU_SIZE),
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
                    ft.Text(label, size=TEXT_SIZE_SMALL, color=PRIMARY_COLOR, font_family=FONT_FAMILY, expand=True),
                ]),
                bgcolor=BLUE_SURFACE if order == self._sort_order else CARD_COLOR,
                padding=ft.Padding.symmetric(horizontal=SORT_OPTION_HORIZONTAL_PADDING, vertical=SORT_OPTION_VERTICAL_PADDING),
                border_radius=SORT_OPTION_RADIUS,
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
