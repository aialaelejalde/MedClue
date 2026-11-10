"""Build small interface parts that several screens share."""

import flet as ft

from medclue_mobile.ui.theme import (
    CARD_COLOR,
    CARD_RADIUS,
    CARD_SPACING,
    CONTENT_PADDING,
    ICON_SIZE,
    PRIMARY_COLOR,
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


def use_chips(uses: list[str]) -> ft.Row:
    """Create chips to display medication uses."""
    return ft.Row(
        controls=[
            ft.Chip(label=ft.Text(use, theme_style=ft.TextThemeStyle.BODY_MEDIUM))
            for use in uses
        ],
        wrap=True,
        spacing=CARD_SPACING,
        run_spacing=CARD_SPACING,
    )


def medication_photo(
    photo: bytes | None,
    *,
    height: float,
    width: float | None = None,
    fit: ft.BoxFit = ft.BoxFit.CONTAIN,
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
            width=width,
            fit=fit,
            semantics_label="Medication photo",
            error_content=placeholder,
        )
        if photo else placeholder
    )
    return ft.Container(
        content=content,
        width=width,
        height=height,
        alignment=ft.Alignment.CENTER,
        bgcolor=CARD_COLOR,
        border_radius=CARD_RADIUS,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )
