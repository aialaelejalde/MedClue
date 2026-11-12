"""Build small interface parts that several screens share."""

import flet as ft

from medclue_mobile.ui.theme import (
    CARD_COLOR,
    CARD_RADIUS,
    CARD_SPACING,
    ACCENT_COLOR,
    CONTENT_PADDING,
    ICON_SIZE,
    PRIMARY_COLOR,
    TEXT_COLOR,
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
            controls=[ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_LARGE), *controls],
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
    )


def _use_chip(use: str) -> ft.Container:
    return ft.Container(
        content=ft.Text(
            use, color=TEXT_COLOR, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border=ft.Border.all(1, ACCENT_COLOR),
        border_radius=24,
        bgcolor=CARD_COLOR,
        tooltip=use,
    )


def use_chips(uses: list[str], *, compact: bool = False) -> ft.Control:
    """Keep original labels and measure compact chips using the device's font."""
    if compact and uses:
        return _CompactUseChips(uses)
    return ft.Row(
        controls=[_use_chip(use) for use in uses],
        wrap=True,
        spacing=CARD_SPACING,
        run_spacing=CARD_SPACING,
    )


class _CompactUseChips(ft.Stack):
    """Measure natural widths offscreen, then fit one row with an overflow count."""

    def __init__(self, uses: list[str]):
        super().__init__(on_size_change=self._resized)
        self._uses = list(uses)
        self._widths: dict[str, float] = {}
        self._available = 0.0
        self._layout = None
        self._chips = [_use_chip(use) for use in uses]
        self._chips[0].expand = True
        self._row = ft.Row(controls=[self._chips[0]], spacing=CARD_SPACING, opacity=0)
        measurements = []
        for index, use in enumerate(uses):
            chip = _use_chip(use)
            chip.on_size_change = self._measure(f"use:{index}")
            measurements.append(chip)
        ellipsis = _use_chip("…")
        ellipsis.on_size_change = self._measure("ellipsis")
        measurements.append(ellipsis)
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
        if self._available <= 0 or len(self._widths) < total * 2 + 1:
            return
        natural = [self._widths[f"use:{index}"] for index in range(total)]
        visible_widths = []
        for count in range(total, 0, -1):
            hidden = total - count
            counter_width = self._widths[f"count:{hidden}"] if hidden else 0
            gaps = CARD_SPACING * (count if hidden else count - 1)
            remaining = self._available - sum(natural[:count - 1]) - gaps - counter_width
            if remaining >= min(natural[count - 1], self._widths["ellipsis"]):
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
                tooltip="\n".join(self._uses[len(visible_widths):]),
                width=min(self._available, self._widths[f"count:{hidden}"]),
                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
            ))
        self._row.controls = controls
        self._row.opacity = 1
        if self.parent is not None:
            self.update()


def floating_action_spacer(button: ft.FloatingActionButton, *, spacing: int) -> ft.Container:
    """Reserve the button's measured height without adding another full gap."""
    spacer = ft.Container(height=0)

    def resized(event: ft.LayoutSizeChangeEvent) -> None:
        spacer.height = max(0, event.height - spacing)
        if spacer.parent is not None:
            spacer.update()

    button.on_size_change = resized
    return spacer


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
        bgcolor=CARD_COLOR,
        border_radius=CARD_RADIUS,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )
