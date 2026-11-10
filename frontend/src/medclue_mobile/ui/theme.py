"""Define the app colors, text styles, and spacing."""

import flet as ft


BACKGROUND_COLOR = "#FFFFFF"
CARD_COLOR = "#F2F4FB"
PRIMARY_COLOR = "#687FA5"
ACCENT_COLOR = "#B9A3D4"
TEXT_COLOR = "#30394F"

FONT_FAMILY = "Roboto"
SCREEN_MARGIN = 16
CARD_SPACING = 12
CONTENT_PADDING = 16
SECTION_SPACING = 24
CARD_RADIUS = 16
BUTTON_RADIUS = 12
MIN_TOUCH_TARGET_SIZE = 48
ICON_SIZE = 24


def create_theme() -> ft.Theme:
    button_style = ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS))

    return ft.Theme(
        use_material3=True,
        font_family=FONT_FAMILY,
        color_scheme_seed=PRIMARY_COLOR,
        color_scheme=ft.ColorScheme(
            primary=PRIMARY_COLOR,
            on_primary=BACKGROUND_COLOR,
            primary_container=CARD_COLOR,
            on_primary_container=TEXT_COLOR,
            secondary=ACCENT_COLOR,
            on_secondary=TEXT_COLOR,
            secondary_container=CARD_COLOR,
            on_secondary_container=TEXT_COLOR,
            surface=BACKGROUND_COLOR,
            on_surface=TEXT_COLOR,
            on_surface_variant=TEXT_COLOR,
            surface_container=CARD_COLOR,
            outline=ACCENT_COLOR,
            outline_variant=ACCENT_COLOR,
        ),
        scaffold_bgcolor=BACKGROUND_COLOR,
        text_theme=ft.TextTheme(
            headline_large=ft.TextStyle(size=32, color=TEXT_COLOR),
            title_large=ft.TextStyle(size=22, color=TEXT_COLOR),
            title_medium=ft.TextStyle(size=16, color=TEXT_COLOR, weight=ft.FontWeight.W_500),
            body_large=ft.TextStyle(size=16, color=TEXT_COLOR),
            body_medium=ft.TextStyle(size=14, color=TEXT_COLOR),
            body_small=ft.TextStyle(size=12, color=TEXT_COLOR),
        ),
        card_theme=ft.CardTheme(
            color=CARD_COLOR,
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=CARD_RADIUS),
        ),
        chip_theme=ft.ChipTheme(
            bgcolor=CARD_COLOR,
            selected_color=ACCENT_COLOR,
            label_text_style=ft.TextStyle(size=14, color=TEXT_COLOR),
            border_side=ft.BorderSide(color=ACCENT_COLOR),
            shape=ft.StadiumBorder(),
        ),
        button_theme=ft.ButtonTheme(style=button_style),
        filled_button_theme=ft.FilledButtonTheme(style=button_style),
        outlined_button_theme=ft.OutlinedButtonTheme(style=button_style),
        text_button_theme=ft.TextButtonTheme(style=button_style),
        icon_theme=ft.IconTheme(color=PRIMARY_COLOR, size=ICON_SIZE),
    )
