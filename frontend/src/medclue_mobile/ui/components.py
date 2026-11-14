"""Build small interface parts that several screens share."""

import re
import math
from datetime import date

import flet as ft
import flet.canvas as cv
from babel import UnknownLocaleError
from babel.dates import format_date

from medclue_mobile.ui.theme import (
    CARD_COLOR,
    CARD_RADIUS,
    CARD_SPACING,
    CONTENT_PADDING,
    ICON_SIZE,
    PRIMARY_COLOR,
    TEXT_COLOR,
    BACKGROUND_COLOR, BLUE_BORDER, BLUE_SURFACE, LAVENDER_SURFACE, LAVENDER_TEXT,
    SECONDARY_TEXT_COLOR, SUCCESS_COLOR, SUCCESS_SURFACE, WARNING_COLOR,
    WARNING_SURFACE, DANGER_COLOR, DANGER_SURFACE, action_style,
    ACCENT_COLOR, FONT_FAMILY, INPUT_TEXT_SIZE, SECTION_SPACING, SCREEN_MARGIN,
)


@ft.control("TextField")
class _DismissibleTextField(ft.TextField):
    # Flet's Flutter TextField supports a changing blur token, but the Python
    # TextField does not expose it yet. Declare it so it is serialized normally.
    blur: str = "0"


def text_field(**kwargs) -> ft.TextField:
    field = _DismissibleTextField(
        text_size=INPUT_TEXT_SIZE, color=TEXT_COLOR,
        text_style=ft.TextStyle(size=INPUT_TEXT_SIZE, color=TEXT_COLOR, font_family=FONT_FAMILY),
        label_style=ft.TextStyle(size=INPUT_TEXT_SIZE, color=PRIMARY_COLOR, font_family=FONT_FAMILY),
        hint_style=ft.TextStyle(size=INPUT_TEXT_SIZE, color=PRIMARY_COLOR, font_family=FONT_FAMILY),
        **kwargs,
    )

    def dismiss_keyboard(event: ft.Event) -> None:
        field.blur = str(int(field.blur) + 1)
        if field.parent is not None:
            field.update()

    field.on_tap_outside = dismiss_keyboard
    return field


def camera_guide(*, visible: bool = True) -> ft.Container:
    def corner(*, flip_x: bool = False, flip_y: bool = False, **position) -> cv.Canvas:
        def point(x: float, y: float) -> tuple[float, float]:
            return (24 - x if flip_x else x, 24 - y if flip_y else y)

        return cv.Canvas(
            shapes=[cv.Path(
                elements=[
                    cv.Path.MoveTo(*point(1, 23)), cv.Path.LineTo(*point(1, 8)),
                    cv.Path.QuadraticTo(*point(1, 1), *point(8, 1), w=math.sqrt(0.5)),
                    cv.Path.LineTo(*point(23, 1)),
                ],
                paint=ft.Paint(color=ACCENT_COLOR, stroke_width=2,
                               style=ft.PaintingStyle.STROKE,
                               stroke_cap=ft.StrokeCap.ROUND, stroke_join=ft.StrokeJoin.ROUND),
            )],
            width=24, height=24, **position,
        )

    return ft.Container(
        content=ft.Stack([
            corner(top=0, left=0),
            corner(flip_x=True, top=0, right=0),
            corner(flip_y=True, bottom=0, left=0),
            corner(flip_x=True, flip_y=True, bottom=0, right=0),
        ]),
        margin=SECTION_SPACING, visible=visible, ignore_interactions=True,
        border=ft.Border.all(0.5, ACCENT_COLOR), border_radius=8,
    )


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
            color=ft.Colors.with_opacity(0.08, TEXT_COLOR),
            blur_radius=8,
            spread_radius=0,
            offset=ft.Offset(0, 1),
        ),
        padding=padding,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ink=on_click is not None,
        on_click=on_click,
    )


def soft_section(title: str, controls: list[ft.Control], *, spacing: int = CARD_SPACING) -> ft.Container:
    return soft_card(
        ft.Column(
            controls=[ft.Text(title.upper(), size=12, color=SECONDARY_TEXT_COLOR, weight=ft.FontWeight.W_600), *controls],
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


def _use_chip(use: str, *, full_text: bool = False, display_text: str | None = None) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            use if display_text is None else display_text, color=LAVENDER_TEXT,
            max_lines=None if full_text else 1,
            overflow=None if full_text else ft.TextOverflow.ELLIPSIS,
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border=ft.Border.all(0, ft.Colors.TRANSPARENT),
        border_radius=24,
        bgcolor=LAVENDER_SURFACE,
        tooltip=use,
    )


def use_chips(uses: list[str], *, compact: bool = False, full_text: bool = False) -> ft.Control:
    """Show compact summaries or complete labels without changing saved text."""
    if compact and uses:
        return _CompactUseChips(uses)
    return ft.Row(
        controls=[_use_chip(use, full_text=full_text) for use in uses],
        wrap=True,
        spacing=CARD_SPACING,
        run_spacing=CARD_SPACING,
    )


class _CompactUseChips(ft.Container):
    """Fit the actual chips into one row, reserving space for the overflow count."""

    def __init__(self, uses: list[str]):
        super().__init__(on_size_change=self._resized)
        self._uses = list(uses)
        labels = [_home_use_label(use) for use in uses]
        self._indices = [index for index, label in enumerate(labels) if label]
        self._widths: dict[str, float] = {}
        self._available = 0.0
        self._layout = None
        self._chips = [_use_chip(uses[index], display_text=labels[index]) for index in self._indices]
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

    def _measure(self, index: int):
        def measured(event: ft.LayoutSizeChangeEvent) -> None:
            if self._chips[index].width is None:
                self._widths[f"use:{index}"] = event.width
                self._fit()
        return measured

    def _measure_counter(self, event: ft.LayoutSizeChangeEvent) -> None:
        self._counter_width = event.width
        self._fit()

    def _resized(self, event: ft.LayoutSizeChangeEvent) -> None:
        self._available = max(0, event.width)
        self._fit()

    def _fit(self) -> None:
        total = len(self._uses)
        countable = len(self._chips)
        if self._available <= 0 or any(f"use:{i}" not in self._widths for i in range(countable)):
            return
        if not self._counter_width:
            return
        natural = [self._widths[f"use:{index}"] for index in range(countable)]
        visible_widths = []
        for count in range(countable, 0, -1):
            hidden = total - count
            counter_width = self._counter_width if hidden else 0
            gaps = CARD_SPACING * (count if hidden else count - 1)
            remaining = self._available - sum(natural[:count - 1]) - gaps - counter_width
            if remaining >= natural[count - 1] or (count == 1 and remaining > 24):
                visible_widths = natural[:count - 1] + [min(natural[count - 1], remaining)]
                break
        hidden = total - len(visible_widths)
        layout = (tuple(visible_widths), hidden, self._available)
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
                use for index, use in enumerate(self._uses) if index not in self._indices[:len(visible_widths)]
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


def action_button(
    label: str,
    on_click: ft.ControlEventHandler[ft.FilledButton],
    *,
    icon: ft.IconData | None = None,
    kind: str = "primary",
) -> ft.FilledButton:
    if label.startswith("Save"):
        icon = ft.Icons.SAVE_OUTLINED
    return ft.FilledButton(
        label, icon=retry_icon() if label == "Try again" else (ft.Icon(icon, size=20) if icon else None), on_click=on_click,
        style=action_style(kind), elevation=0,
        expand=True,
    )


def retry_icon() -> ft.Icon:
    return ft.Icon(ft.Icons.SYNC, size=20, rotate=math.pi / 2)


def medication_subtitle(strength: str | None, form: str | None, *, max_lines: int | None = None) -> ft.Text:
    return ft.Text(
        " · ".join(value.strip() for value in (strength, form) if value and value.strip()),
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        visible=bool(strength or form),
        max_lines=max_lines, overflow=ft.TextOverflow.ELLIPSIS if max_lines else None,
    )


def status_photo(photo: bytes | None, status: str, label: str) -> ft.Stack:
    color, surface, icon = {
        "verified": (SUCCESS_COLOR, SUCCESS_SURFACE, ft.Icons.CHECK_CIRCLE_OUTLINE),
        "possible": (WARNING_COLOR, WARNING_SURFACE, ft.Icons.WARNING_AMBER_ROUNDED),
        "unidentified": (DANGER_COLOR, DANGER_SURFACE, ft.Icons.CANCEL_OUTLINED),
    }[status]
    badge = ft.Container(
        content=ft.Row([
            ft.Icon(icon, color=color, size=18),
            ft.Text(label, color=color, size=12, weight=ft.FontWeight.W_600),
        ], spacing=6, tight=True),
        bgcolor=surface, border_radius=24, padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        left=12, bottom=12,
    )
    return ft.Stack([
        medication_photo(photo, height=180, aspect_ratio=4 / 3, fit=ft.BoxFit.COVER), badge,
    ])


def result_layout(
    controls: list[ft.Control], actions: list[ft.Control], *,
    center_information: bool = False, action_spacing: float = CONTENT_PADDING,
) -> ft.SafeArea:
    """Scroll the whole result card, including its trailing actions."""
    card = soft_card(ft.Column([
        ft.Column(controls=controls, spacing=CARD_SPACING, tight=True,
                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        ft.Column([ft.Row([action]) for action in actions], spacing=8,
                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH, tight=True),
    ], spacing=action_spacing, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH))
    viewport = ft.ListView([card], expand=True, padding=ft.Padding.symmetric(vertical=SCREEN_MARGIN))
    viewport.on_size_change = stretch_card(card, center_information=center_information)
    return ft.SafeArea(content=viewport, expand=True, avoid_intrusions_top=False, avoid_intrusions_bottom=False)


def stretch_card(
    card: ft.Container, leading: ft.Control | None = None, *,
    leading_spacing: float = CARD_SPACING, center_information: bool = True,
):
    """Distribute spare viewport space as padding, preserving natural content sizes."""
    sizes: dict[str, float] = {}
    information, actions = card.content.controls
    centered_information = ft.Container(content=information)
    card.content.controls[0] = centered_information
    extra = 0.0

    def measured(key: str):
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
            if abs(extra - padding) > 0.5:
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


def match_option(
    name: str,
    strength: str | None,
    form: str | None,
    *,
    selected: bool = False,
    show_selection: bool = True,
    on_click: ft.ControlEventHandler[ft.Container] | None = None,
) -> ft.Container:
    return ft.Container(
        content=ft.Row([
            ft.Column([medication_name(name), medication_subtitle(strength, form)],
                      spacing=4, tight=True, expand=True),
            ft.Container(
                content=ft.Icon(ft.Icons.CHECK, color=CARD_COLOR, size=16) if selected else None,
                width=24, height=24, border_radius=12,
                border=ft.Border.all(1, PRIMARY_COLOR if selected else BLUE_BORDER),
                bgcolor=PRIMARY_COLOR if selected else CARD_COLOR,
                alignment=ft.Alignment.CENTER,
                visible=show_selection,
            ),
        ], spacing=CARD_SPACING),
        padding=CONTENT_PADDING, border_radius=12,
        bgcolor=BLUE_SURFACE if selected else CARD_COLOR,
        border=ft.Border.all(2 if selected else 1, PRIMARY_COLOR if selected else BLUE_BORDER),
        on_click=on_click, ink=on_click is not None,
    )


def information_row(label: str, value: str | ft.Text) -> ft.Container:
    text = value if isinstance(value, ft.Text) else ft.Text(value)
    text.color, text.expand, text.text_align = TEXT_COLOR, 2, ft.TextAlign.RIGHT
    return ft.Container(
        content=ft.Row([
            ft.Text(label, theme_style=ft.TextThemeStyle.BODY_MEDIUM, no_wrap=True),
            text,
        ], spacing=CARD_SPACING),
        padding=CONTENT_PADDING, bgcolor=BACKGROUND_COLOR, border_radius=12,
    )


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
