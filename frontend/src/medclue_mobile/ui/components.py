"""Build small interface parts that several screens share."""

import re

import flet as ft

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
    WARNING_SURFACE, DANGER_COLOR, DANGER_SURFACE, MIN_TOUCH_TARGET_SIZE, action_style,
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


class _CompactUseChips(ft.Stack):
    """Measure natural widths offscreen, then fit one row with an overflow count."""

    def __init__(self, uses: list[str]):
        super().__init__(on_size_change=self._resized)
        self._uses = list(uses)
        labels = [_home_use_label(use) for use in uses]
        self._indices = [index for index, label in enumerate(labels) if label]
        self._widths: dict[str, float] = {}
        self._available = 0.0
        self._layout = None
        self._chips = [_use_chip(uses[index], display_text=labels[index]) for index in self._indices]
        self._row = ft.Row(spacing=CARD_SPACING, opacity=0)
        measurements = []
        for index, original_index in enumerate(self._indices):
            label = labels[original_index]
            chip = _use_chip(label)
            chip.on_size_change = self._measure(f"use:{index}")
            measurements.append(chip)
            # Require a readable prefix as well as the ellipsis when truncating.
            minimum = _use_chip(label[:3] + "…")
            minimum.on_size_change = self._measure(f"minimum:{index}")
            measurements.append(minimum)
        for count in range(1, len(uses) + 1):
            measurements.append(ft.Text(
                f"+{count}", theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                on_size_change=self._measure(f"count:{count}"),
            ))
        self.controls = [
            self._row,
            ft.Container(
                content=ft.Semantics(
                    content=ft.Row(controls=measurements, scroll=ft.ScrollMode.HIDDEN),
                    hidden=True, exclude_semantics=True,
                ),
                opacity=0, ignore_interactions=True,
                top=0, left=0, right=0, height=0,
            ),
        ]

    def _measure(self, key: str):
        def measured(event: ft.LayoutSizeChangeEvent) -> None:
            self._widths[key] = event.width
            self._fit()
        return measured

    def _resized(self, event: ft.LayoutSizeChangeEvent) -> None:
        self._available = max(0, event.width)
        self._fit()

    def _fit(self) -> None:
        total = len(self._uses)
        countable = len(self._chips)
        if self._available <= 0 or len(self._widths) < countable * 2 + total:
            return
        natural = [self._widths[f"use:{index}"] for index in range(countable)]
        visible_widths = []
        for count in range(countable, 0, -1):
            hidden = total - count
            counter_width = self._widths[f"count:{hidden}"] if hidden else 0
            gaps = CARD_SPACING * (count if hidden else count - 1)
            remaining = self._available - sum(natural[:count - 1]) - gaps - counter_width
            minimum_width = min(natural[count - 1], self._widths[f"minimum:{count - 1}"])
            if remaining >= minimum_width:
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
            controls.append(ft.Text(
                f"+{hidden}", color=TEXT_COLOR, theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                tooltip="\n".join(
                    use for index, use in enumerate(self._uses) if index not in self._indices[:len(visible_widths)]
                ),
                width=min(self._available, self._widths[f"count:{hidden}"]),
                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
            ))
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
    rounded: bool = True,
) -> ft.FilledButton:
    return ft.FilledButton(
        label, icon=ft.Icon(icon, size=20) if icon else None, on_click=on_click,
        style=action_style(kind, rounded=rounded), elevation=0,
        expand=True, height=MIN_TOUCH_TARGET_SIZE,
    )


def medication_subtitle(strength: str | None, form: str | None) -> ft.Text:
    return ft.Text(
        " · ".join(value.strip() for value in (strength, form) if value and value.strip()),
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        visible=bool(strength or form),
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


def result_layout(controls: list[ft.Control], actions: list[ft.Control]) -> ft.SafeArea:
    """One white result card with scrollable information and accessible bottom actions."""
    card = soft_card(ft.Column([
        ft.ListView(controls=controls, spacing=CARD_SPACING, expand=True),
        ft.Column([ft.Row([action]) for action in actions], spacing=8,
                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH, tight=True),
    ], spacing=CONTENT_PADDING, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH))
    card.expand = True
    return ft.SafeArea(content=card, expand=True)


def match_option(
    name: str,
    strength: str | None,
    form: str | None,
    *,
    selected: bool = False,
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
            ),
        ], spacing=CARD_SPACING),
        padding=CONTENT_PADDING, border_radius=12,
        bgcolor=BLUE_SURFACE if selected else CARD_COLOR,
        border=ft.Border.all(2 if selected else 1, PRIMARY_COLOR if selected else BLUE_BORDER),
        on_click=on_click, ink=on_click is not None,
    )


def information_row(label: str, value: str) -> ft.Container:
    return ft.Container(
        content=ft.Row([
            ft.Text(label, theme_style=ft.TextThemeStyle.BODY_MEDIUM, expand=True),
            ft.Text(value, color=TEXT_COLOR, weight=ft.FontWeight.W_700, expand=2, text_align=ft.TextAlign.RIGHT),
        ], spacing=CARD_SPACING),
        padding=CONTENT_PADDING, bgcolor=BACKGROUND_COLOR, border_radius=12,
    )
