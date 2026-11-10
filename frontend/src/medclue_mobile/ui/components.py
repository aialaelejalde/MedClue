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
        padding=padding,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ink=on_click is not None,
        on_click=on_click,
    )


def soft_section(title: str, controls: list[ft.Control]) -> ft.Container:
    return soft_card(
        ft.Column(
            controls=[ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_LARGE), *controls],
            spacing=CARD_SPACING,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    )


def medication_name(
    name: str | None,
    *,
    theme_style: ft.TextThemeStyle = ft.TextThemeStyle.TITLE_MEDIUM,
) -> ft.Text:
    return ft.Text(
        (name or "").strip() or "Unknown medication",
        theme_style=theme_style,
    )


def use_chips(uses: list[str], *, compact: bool = False) -> ft.Row:
    """Keep long labels inside the available width without changing saved text."""
    chips = [
        ft.Container(
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
        for use in uses
    ]
    row = ft.Row(
        controls=chips if not compact else [],
        wrap=not compact,
        spacing=CARD_SPACING,
        run_spacing=CARD_SPACING,
    )
    if not compact or not uses:
        return row

    def resize(event: ft.LayoutSizeChangeEvent) -> None:
        available = max(0, event.width)
        count = len(uses)
        while count:
            hidden_count = len(uses) - count
            counter_width = 16 + len(str(hidden_count)) * 8 if hidden_count else 0
            gaps = CARD_SPACING * (count if hidden_count else count - 1)
            if count * 48 + gaps + counter_width <= available:
                break
            count -= 1

        hidden_count = len(uses) - count
        counter_width = 16 + len(str(hidden_count)) * 8 if hidden_count else 0
        gaps = CARD_SPACING * (count if hidden_count else max(0, count - 1))
        budget = max(0, available - gaps - counter_width)
        preferred = [max(48, len(use) * 7 + 26) for use in uses[:count]]
        extra = sum(width - 48 for width in preferred)
        share = min(1, max(0, budget - count * 48) / extra) if extra else 0
        visible = chips[:count]
        for chip, width in zip(visible, preferred):
            chip.width = 48 + (width - 48) * share

        if hidden_count:
            visible.append(ft.Text(
                f"+{hidden_count}", color=TEXT_COLOR,
                tooltip="\n".join(uses[count:]),
                width=min(available, counter_width),
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ))
        row.controls = visible
        row.update()

    row.on_size_change = resize
    return row


def medication_photo(
    photo: bytes | None,
    *,
    height: float,
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
    content = (
        ft.Image(
            src=photo,
            height=height,
            width=width if width is not None else float("inf"),
            fit=fit,
            semantics_label="Medication photo",
            error_content=placeholder,
        )
        if photo else placeholder
    )
    if photo and aspect_ratio is not None:
        content.height = None
        content.width = None
        content = ft.Stack(controls=[content], fit=ft.StackFit.EXPAND)
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
