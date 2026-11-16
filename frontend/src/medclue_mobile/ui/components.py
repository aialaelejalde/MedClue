"""Build small interface parts that several screens share."""

import math
import re
from collections.abc import Callable
from datetime import date

import flet as ft
import flet.canvas as cv
from babel import UnknownLocaleError
from babel.dates import format_date

from medclue_mobile.ui.theme import (
    ACCENT_COLOR,
    BACKGROUND_COLOR,
    BLUE_BORDER,
    BLUE_SURFACE,
    CARD_COLOR,
    CARD_RADIUS,
    CARD_SPACING,
    CONTENT_PADDING,
    DANGER_COLOR,
    DANGER_SURFACE,
    FONT_FAMILY,
    ICON_SIZE,
    LAVENDER_SURFACE,
    LAVENDER_TEXT,
    MEDICATION_PHOTO_HEIGHT,
    PHOTO_FRAME_ASPECT_RATIO,
    PRIMARY_COLOR,
    SCREEN_MARGIN,
    SECONDARY_TEXT_COLOR,
    SECTION_SPACING,
    SMALL_ICON_SIZE,
    SUCCESS_COLOR,
    SUCCESS_SURFACE,
    TEXT_COLOR,
    TEXT_SIZE_MEDIUM,
    TEXT_SIZE_SMALL,
    WARNING_COLOR,
    WARNING_SURFACE,
    action_style,
)


CARD_SHADOW_OPACITY = 0.08
CARD_SHADOW_BLUR_RADIUS = 8
CARD_SHADOW_VERTICAL_OFFSET = 1

USE_CHIP_HORIZONTAL_PADDING = 12
USE_CHIP_VERTICAL_PADDING = 8
USE_CHIP_RADIUS = 24
MIN_COMPACT_USE_WIDTH = 24

CAMERA_GUIDE_CORNER_SIZE = 24
CAMERA_GUIDE_CORNER_INSET = 1
CAMERA_GUIDE_CORNER_ARC_END = 8
CAMERA_GUIDE_STROKE_WIDTH = 2
CAMERA_GUIDE_BORDER_WIDTH = 0.5
CAMERA_GUIDE_RADIUS = 8

STATUS_BADGE_ICON_SIZE = 18
STATUS_BADGE_SPACING = 6
STATUS_BADGE_RADIUS = 24
STATUS_BADGE_HORIZONTAL_PADDING = 12
STATUS_BADGE_VERTICAL_PADDING = 8
STATUS_BADGE_OFFSET = 12

RESULT_ACTION_SPACING = 8
LAYOUT_RESIZE_TOLERANCE = 0.5

MATCH_DETAILS_SPACING = 4
MATCH_OPTION_RADIUS = 12
MATCH_INDICATOR_SIZE = 24
MATCH_CHECK_ICON_SIZE = 16
MATCH_BORDER_WIDTH = 1
MATCH_SELECTED_BORDER_WIDTH = 2

INFORMATION_VALUE_EXPAND = 2
INFORMATION_ROW_RADIUS = 12


@ft.control("TextField")
class _DismissibleTextField(ft.TextField):
    blur: str = "0"


def text_field(**kwargs) -> ft.TextField:
    field = _DismissibleTextField(
        text_size=TEXT_SIZE_MEDIUM, color=TEXT_COLOR,
        text_style=ft.TextStyle(size=TEXT_SIZE_MEDIUM, color=TEXT_COLOR, font_family=FONT_FAMILY),
        label_style=ft.TextStyle(size=TEXT_SIZE_MEDIUM, color=PRIMARY_COLOR, font_family=FONT_FAMILY),
        hint_style=ft.TextStyle(size=TEXT_SIZE_MEDIUM, color=PRIMARY_COLOR, font_family=FONT_FAMILY),
        **kwargs,
    )

    def dismiss_keyboard(event: ft.Event) -> None:
        field.blur = str(int(field.blur) + 1)
        if field.parent is not None:
            field.update()

    field.on_tap_outside = dismiss_keyboard
    return field


def action_button(
    label: str,
    on_click: ft.ControlEventHandler[ft.FilledButton],
    *,
    icon: ft.IconData | ft.Icon | None = None,
    kind: str = "primary",
) -> ft.FilledButton:
    if icon is not None and not isinstance(icon, ft.Icon):
        icon = ft.Icon(icon, size=SMALL_ICON_SIZE)
    return ft.FilledButton(
        label, icon=icon, on_click=on_click,
        style=action_style(kind), elevation=0,
        expand=True,
    )


def retry_icon() -> ft.Icon:
    return ft.Icon(ft.Icons.SYNC, size=SMALL_ICON_SIZE, rotate=math.pi / 2)


def soft_card(
    content: ft.Control,
    *,
    on_click: ft.ControlEventHandler[ft.Container] | None = None,
    padding: int = CONTENT_PADDING,
) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=CARD_COLOR,
        border_radius=CARD_RADIUS,
        shadow=ft.BoxShadow(
            color=ft.Colors.with_opacity(CARD_SHADOW_OPACITY, TEXT_COLOR),
            blur_radius=CARD_SHADOW_BLUR_RADIUS,
            spread_radius=0,
            offset=ft.Offset(0, CARD_SHADOW_VERTICAL_OFFSET),
        ),
        padding=padding,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ink=on_click is not None,
        on_click=on_click,
    )


def soft_section(title: str, controls: list[ft.Control], *, spacing: int = CARD_SPACING) -> ft.Container:
    return soft_card(
        ft.Column(
            controls=[ft.Text(title.upper(), size=TEXT_SIZE_SMALL, color=SECONDARY_TEXT_COLOR, weight=ft.FontWeight.W_600), *controls],
            spacing=spacing,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    )


def medication_name(
    name: str | None,
    *,
    theme_style: ft.TextThemeStyle = ft.TextThemeStyle.TITLE_MEDIUM,
    max_lines: int | None = None,
    text_align: ft.TextAlign | None = None,
) -> ft.Text:
    return ft.Text(
        (name or "").strip() or "Unknown medication",
        theme_style=theme_style,
        max_lines=max_lines,
        overflow=ft.TextOverflow.ELLIPSIS if max_lines is not None else None,
        text_align=text_align,
        weight=ft.FontWeight.W_700,
    )


def medication_subtitle(strength: str | None, form: str | None, *, max_lines: int | None = None) -> ft.Text:
    return ft.Text(
        " · ".join(value.strip() for value in (strength, form) if value and value.strip()),
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        visible=bool(strength or form),
        max_lines=max_lines, overflow=ft.TextOverflow.ELLIPSIS if max_lines else None,
    )


class MatchOption(ft.Container):
    """Display a medication option and manage its selection appearance."""

    def __init__(
        self,
        name: str,
        strength: str | None,
        form: str | None,
        *,
        selected: bool = False,
        show_selection: bool = True,
        on_click: ft.ControlEventHandler[ft.Container] | None = None,
    ):
        indicator = ft.Container(
            width=MATCH_INDICATOR_SIZE, height=MATCH_INDICATOR_SIZE, border_radius=MATCH_INDICATOR_SIZE / 2,
            alignment=ft.Alignment.CENTER,
            visible=show_selection,
        )
        super().__init__(
            content=ft.Row([
                ft.Column([medication_name(name), medication_subtitle(strength, form)],
                          spacing=MATCH_DETAILS_SPACING, tight=True, expand=True),
                indicator,
            ], spacing=CARD_SPACING),
            padding=CONTENT_PADDING, border_radius=MATCH_OPTION_RADIUS,
            on_click=on_click, ink=on_click is not None,
        )
        self._indicator = indicator
        self.set_selected(selected)

    def set_selected(self, selected: bool) -> None:
        """Set the visual appearance of the selection."""
        self.bgcolor = BLUE_SURFACE if selected else CARD_COLOR
        self.border = ft.Border.all(
            MATCH_SELECTED_BORDER_WIDTH if selected else MATCH_BORDER_WIDTH,
            PRIMARY_COLOR if selected else BLUE_BORDER,
        )
        self._indicator.bgcolor = PRIMARY_COLOR if selected else CARD_COLOR
        self._indicator.border = ft.Border.all(MATCH_BORDER_WIDTH, PRIMARY_COLOR if selected else BLUE_BORDER)
        self._indicator.content = ft.Icon(ft.Icons.CHECK, color=CARD_COLOR, size=MATCH_CHECK_ICON_SIZE) if selected else None


def information_row(label: str, value: str | ft.Text) -> ft.Container:
    text = value if isinstance(value, ft.Text) else ft.Text(value)
    text.color, text.expand, text.text_align = TEXT_COLOR, INFORMATION_VALUE_EXPAND, ft.TextAlign.RIGHT
    return ft.Container(
        content=ft.Row([
            ft.Text(label, theme_style=ft.TextThemeStyle.BODY_MEDIUM, no_wrap=True),
            text,
        ], spacing=CARD_SPACING),
        padding=CONTENT_PADDING, bgcolor=BACKGROUND_COLOR, border_radius=INFORMATION_ROW_RADIUS,
    )


def use_chips(uses: list[str], *, compact: bool = False, full_text: bool = False) -> ft.Control:
    if compact and uses:
        return _CompactUseChips(uses)
    return ft.Row(
        controls=[_use_chip(use, full_text=full_text) for use in uses],
        wrap=True,
        spacing=CARD_SPACING,
        run_spacing=CARD_SPACING,
    )


def _use_chip(use: str, *, full_text: bool = False, display_text: str | None = None) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            use if display_text is None else display_text, color=LAVENDER_TEXT,
            max_lines=None if full_text else 1,
            overflow=None if full_text else ft.TextOverflow.ELLIPSIS,
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        ),
        padding=ft.Padding.symmetric(horizontal=USE_CHIP_HORIZONTAL_PADDING, vertical=USE_CHIP_VERTICAL_PADDING),
        border=ft.Border.all(0, ft.Colors.TRANSPARENT),
        border_radius=USE_CHIP_RADIUS,
        bgcolor=LAVENDER_SURFACE,
        tooltip=use,
    )


class _CompactUseChips(ft.Container):
    """Fit the actual chips into one row, reserving space for the overflow count."""

    def __init__(self, uses: list[str]):
        super().__init__(on_size_change=self._resized)
        self._uses = list(uses)
        self._chip_indices = [index for index, use in enumerate(uses) if _home_use_label(use)]
        self._chips = [
            _use_chip(use, display_text=_home_use_label(use))
            for use in uses
            if _home_use_label(use)
        ]
        self._natural_widths: list[float | None] = [None] * len(self._chips)
        self._available_width = 0.0
        self._layout = None
        for index, chip in enumerate(self._chips):
            chip.on_size_change = self._measure(index)
        self._counter_width = 0.0
        self._counter = ft.Text(
            f"+{len(uses)}", color=PRIMARY_COLOR,
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
            on_size_change=self._measure_counter,
        )
        self._row = ft.Row([*self._chips, self._counter], spacing=CARD_SPACING,
                           scroll=ft.ScrollMode.HIDDEN, opacity=0)
        self.content = self._row

    def _measure(self, index: int) -> Callable[[ft.LayoutSizeChangeEvent], None]:
        def measured(event: ft.LayoutSizeChangeEvent) -> None:
            if self._chips[index].width is None:
                self._natural_widths[index] = event.width
                self._fit()
        return measured

    def _measure_counter(self, event: ft.LayoutSizeChangeEvent) -> None:
        self._counter_width = event.width
        self._fit()

    def _resized(self, event: ft.LayoutSizeChangeEvent) -> None:
        self._available_width = max(0, event.width)
        self._fit()

    def _fit(self) -> None:
        total = len(self._uses)
        chip_count = len(self._chips)
        if not chip_count:
            self._counter.value = f"+{total}"
            self._counter.tooltip = "\n".join(self._uses)
            self._row.controls = [self._counter]
            self._row.opacity = 1
            return
        if self._available_width <= 0 or any(width is None for width in self._natural_widths):
            return
        if not self._counter_width:
            return
        natural_widths = [width for width in self._natural_widths if width is not None]
        visible_widths = []
        for count in range(chip_count, 0, -1):
            hidden = total - count
            counter_width = self._counter_width if hidden else 0
            gaps = CARD_SPACING * (count if hidden else count - 1)
            remaining = self._available_width - sum(natural_widths[:count - 1]) - gaps - counter_width
            if remaining >= natural_widths[count - 1] or (count == 1 and remaining > MIN_COMPACT_USE_WIDTH):
                visible_widths = natural_widths[:count - 1] + [min(natural_widths[count - 1], remaining)]
                break
        hidden = total - len(visible_widths)
        layout = (tuple(visible_widths), hidden, self._available_width)
        if layout == self._layout:
            return
        self._layout = layout
        controls = self._chips[:len(visible_widths)]
        for chip, width in zip(controls, visible_widths):
            chip.expand = False
            chip.width = width
        if hidden:
            self._counter.value = f"+{hidden}"
            self._counter.tooltip = "\n".join(
                use for index, use in enumerate(self._uses)
                if index not in self._chip_indices[:len(visible_widths)]
            )
            controls.append(self._counter)
        self._row.controls = controls
        self._row.opacity = 1
        if self.parent is not None:
            self.update()


def _home_use_label(use: str) -> str:
    """Shorten Home labels without changing the full text used by other screens."""
    label = use
    while True:
        simplified = re.sub(r"\([^()]*\)", " ", label)
        if simplified == label:
            return " ".join(label.split())
        label = simplified


def medication_photo(
    photo: bytes | None,
    *,
    height: float | None,
    width: float | None = None,
    fit: ft.BoxFit = ft.BoxFit.CONTAIN,
    aspect_ratio: float | None = None,
) -> ft.Container:
    placeholder = ft.Icon(
        ft.Icons.CAMERA_ALT_OUTLINED,
        size=ICON_SIZE,
        color=PRIMARY_COLOR,
        semantics_label="No medication photo",
    )
    if photo:
        fill_frame = aspect_ratio is not None or height is None
        image = ft.Image(
            src=photo,
            height=None if fill_frame else height,
            width=None if fill_frame else (width if width is not None else float("inf")),
            fit=fit,
            semantics_label="Medication photo",
            error_content=placeholder,
        )
        content = ft.Stack(controls=[image], fit=ft.StackFit.EXPAND) if fill_frame else image
    else:
        content = placeholder
    return ft.Container(
        content=content,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        alignment=ft.Alignment.CENTER,
        bgcolor=BACKGROUND_COLOR,
        border_radius=CARD_RADIUS,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


def status_photo(photo: bytes | None, status: str, label: str) -> ft.Stack:
    color, surface, icon = {
        "verified": (SUCCESS_COLOR, SUCCESS_SURFACE, ft.Icons.CHECK_CIRCLE_OUTLINE),
        "possible": (WARNING_COLOR, WARNING_SURFACE, ft.Icons.WARNING_AMBER_ROUNDED),
        "unidentified": (DANGER_COLOR, DANGER_SURFACE, ft.Icons.CANCEL_OUTLINED),
    }[status]
    badge = ft.Container(
        content=ft.Row([
            ft.Icon(icon, color=color, size=STATUS_BADGE_ICON_SIZE),
            ft.Text(label, color=color, size=TEXT_SIZE_SMALL, weight=ft.FontWeight.W_600),
        ], spacing=STATUS_BADGE_SPACING, tight=True),
        bgcolor=surface, border_radius=STATUS_BADGE_RADIUS,
        padding=ft.Padding.symmetric(horizontal=STATUS_BADGE_HORIZONTAL_PADDING, vertical=STATUS_BADGE_VERTICAL_PADDING),
        left=STATUS_BADGE_OFFSET, bottom=STATUS_BADGE_OFFSET,
    )
    return ft.Stack([
        medication_photo(photo, height=MEDICATION_PHOTO_HEIGHT, aspect_ratio=PHOTO_FRAME_ASPECT_RATIO, fit=ft.BoxFit.COVER), badge,
    ])


def camera_guide(*, visible: bool = True) -> ft.Container:
    def corner(*, flip_x: bool = False, flip_y: bool = False, **position) -> cv.Canvas:
        def point(x: float, y: float) -> tuple[float, float]:
            return (
                CAMERA_GUIDE_CORNER_SIZE - x if flip_x else x,
                CAMERA_GUIDE_CORNER_SIZE - y if flip_y else y,
            )

        inset = CAMERA_GUIDE_CORNER_INSET
        edge = CAMERA_GUIDE_CORNER_SIZE - inset
        arc_end = CAMERA_GUIDE_CORNER_ARC_END
        return cv.Canvas(
            shapes=[cv.Path(
                elements=[
                    cv.Path.MoveTo(*point(inset, edge)), cv.Path.LineTo(*point(inset, arc_end)),
                    cv.Path.QuadraticTo(*point(inset, inset), *point(arc_end, inset), w=math.sqrt(0.5)),
                    cv.Path.LineTo(*point(edge, inset)),
                ],
                paint=ft.Paint(color=ACCENT_COLOR, stroke_width=CAMERA_GUIDE_STROKE_WIDTH,
                               style=ft.PaintingStyle.STROKE,
                               stroke_cap=ft.StrokeCap.ROUND, stroke_join=ft.StrokeJoin.ROUND),
            )],
            width=CAMERA_GUIDE_CORNER_SIZE, height=CAMERA_GUIDE_CORNER_SIZE, **position,
        )

    return ft.Container(
        content=ft.Stack([
            corner(top=0, left=0),
            corner(flip_x=True, top=0, right=0),
            corner(flip_y=True, bottom=0, left=0),
            corner(flip_x=True, flip_y=True, bottom=0, right=0),
        ]),
        margin=SECTION_SPACING, visible=visible, ignore_interactions=True,
        border=ft.Border.all(CAMERA_GUIDE_BORDER_WIDTH, ACCENT_COLOR), border_radius=CAMERA_GUIDE_RADIUS,
    )


def result_layout(
    controls: list[ft.Control], actions: list[ft.Control], *,
    center_information: bool = False, action_spacing: float = CONTENT_PADDING,
) -> ft.SafeArea:
    """Scroll the whole result card, including its actions."""
    card = soft_card(ft.Column([
        ft.Column(controls=controls, spacing=CARD_SPACING, tight=True,
                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        ft.Column([ft.Row([action]) for action in actions], spacing=RESULT_ACTION_SPACING,
                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH, tight=True),
    ], spacing=action_spacing, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH))
    viewport = ft.ListView([card], expand=True, padding=ft.Padding.symmetric(vertical=SCREEN_MARGIN))
    viewport.on_size_change = stretch_card(card, center_information=center_information)
    return ft.SafeArea(content=viewport, expand=True, avoid_intrusions_top=False, avoid_intrusions_bottom=False)


def stretch_card(
    card: ft.Container, leading: ft.Control | None = None, *,
    leading_spacing: float = CARD_SPACING, center_information: bool = True,
) -> Callable[[ft.LayoutSizeChangeEvent], None]:
    """Adjust card layout and alignment when its size changes."""
    sizes: dict[str, float] = {}
    information, actions = card.content.controls
    centered_information = ft.Container(content=information)
    card.content.controls[0] = centered_information
    extra = 0.0

    def measured(key: str) -> Callable[[ft.LayoutSizeChangeEvent], None]:
        def resize(event: ft.LayoutSizeChangeEvent) -> None:
            nonlocal extra
            sizes[key] = event.height
            if not all(name in sizes for name in ("viewport", "information", "actions")):
                return
            if leading is not None and "leading" not in sizes:
                return
            available = sizes["viewport"] - SCREEN_MARGIN * 2 - CONTENT_PADDING * 2
            if leading is not None:
                available -= sizes["leading"] + leading_spacing
            natural_height = sizes["information"] + card.content.spacing + sizes["actions"]
            padding = max(0, available - natural_height)
            if abs(extra - padding) > LAYOUT_RESIZE_TOLERANCE:
                extra = padding
                centered_information.padding = (
                    ft.Padding.symmetric(vertical=padding / 2) if center_information
                    else ft.Padding.only(bottom=padding)
                )
                if card.parent is not None:
                    card.update()
        return resize

    information.on_size_change = measured("information")
    actions.on_size_change = measured("actions")
    if leading is not None:
        leading.on_size_change = measured("leading")
    return measured("viewport")


async def device_date_locale(page: ft.Page) -> ft.Locale | None:
    try:
        device = await page.get_device_info()
    except ft.FletException:
        return None
    return device.locales[0] if device is not None and device.locales else None


def date_label(value: date, locale: ft.Locale | None) -> str:
    if locale is None:
        return value.isoformat()
    try:
        return format_date(value, format="short", locale=str(locale))
    except (UnknownLocaleError, ValueError):
        return value.isoformat()


class DeviceDate(ft.Text):
    """Format a displayed date once the device's regional preferences are available."""

    def __init__(self, value: date):
        super().__init__(value=value.isoformat())
        self._date = value
        self._format_task = None

    def did_mount(self) -> None:
        self._format_task = self.page.run_task(self._format_date)

    def will_unmount(self) -> None:
        if self._format_task is not None:
            self._format_task.cancel()

    async def _format_date(self) -> None:
        self.value = date_label(self._date, await device_date_locale(self.page))
        self.update()
