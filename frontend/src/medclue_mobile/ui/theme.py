"""Define MedClue's visual styles and theme."""

import flet as ft

BACKGROUND_COLOR = "#F2F4FB"
CARD_COLOR = "#FFFFFF"
PRIMARY_COLOR = "#687FA5"
ACCENT_COLOR = "#B9A3D4"
TEXT_COLOR = "#30394F"
SECONDARY_TEXT_COLOR = PRIMARY_COLOR
LAVENDER_SURFACE = "#F0EAF6"
LAVENDER_TEXT = "#80639F"
BLUE_SURFACE = "#E8EEF7"
BLUE_BORDER = "#D7E0EE"
SUCCESS_COLOR = "#32805A"
SUCCESS_SURFACE = "#EAF6EF"
WARNING_COLOR = "#997940"
WARNING_SURFACE = "#FFF6DE"
DANGER_COLOR = "#DC2626"
DANGER_SURFACE = "#FEF2F2"

FONT_FAMILY = "Plus Jakarta Sans"
TEXT_SIZE_SMALL = 12
TEXT_SIZE_MEDIUM = 14
TEXT_SIZE_LARGE = 16
TITLE_TEXT_SIZE = 20
HEADLINE_TEXT_SIZE = 24

SCREEN_MARGIN = 16
CARD_SPACING = 12
CONTENT_PADDING = 16
SECTION_SPACING = 24
CARD_RADIUS = 20
BUTTON_RADIUS = 28
INPUT_RADIUS = 12
BAR_HEIGHT = 64
HEADER_HEIGHT = 52
MIN_TOUCH_TARGET_SIZE = 48
ICON_SIZE = 24
SMALL_ICON_SIZE = 20

MEDICATION_PHOTO_HEIGHT = 180
PHOTO_FRAME_ASPECT_RATIO = 4 / 3
CAMERA_FRAME_RADIUS = 16

ACTION_BUTTON_PADDING_HORIZONTAL = 20
ACTION_BUTTON_PADDING_VERTICAL = 14
BUTTON_ANIMATION_DURATION_MS = 150
ACTION_PRESSED_OPACITY = 0.18
CONTROL_PRESSED_OPACITY = 0.14
NAVIGATION_LABEL_BOTTOM_PADDING = 4


@ft.value
class _ActionButtonStyle(ft.ButtonStyle):
    minimum_size: ft.ControlStateValue[ft.Size] | None = None


def action_style(kind: str = "primary") -> ft.ButtonStyle:
    foreground, background = {
        "primary": (CARD_COLOR, PRIMARY_COLOR),
        "secondary": (LAVENDER_TEXT, LAVENDER_SURFACE),
        "tertiary": (PRIMARY_COLOR, CARD_COLOR),
        "danger": (DANGER_COLOR, DANGER_SURFACE),
    }[kind]
    return _ActionButtonStyle(
        color={ft.ControlState.DEFAULT: foreground, ft.ControlState.DISABLED: SECONDARY_TEXT_COLOR},
        bgcolor={ft.ControlState.DEFAULT: background, ft.ControlState.DISABLED: BACKGROUND_COLOR},
        side=ft.BorderSide(1, BLUE_BORDER) if kind == "tertiary" else ft.BorderSide(0, ft.Colors.TRANSPARENT),
        shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS),
        padding={ft.ControlState.DEFAULT: ft.Padding.symmetric(horizontal=ACTION_BUTTON_PADDING_HORIZONTAL, vertical=ACTION_BUTTON_PADDING_VERTICAL)},
        minimum_size={ft.ControlState.DEFAULT: ft.Size(0, MIN_TOUCH_TARGET_SIZE)},
        text_style=ft.TextStyle(size=TEXT_SIZE_MEDIUM, weight=ft.FontWeight.W_600, font_family=FONT_FAMILY),
        elevation=0,
        overlay_color={ft.ControlState.PRESSED: ft.Colors.with_opacity(ACTION_PRESSED_OPACITY, foreground)},
        animation_duration=BUTTON_ANIMATION_DURATION_MS,
    )


def create_theme() -> ft.Theme:
    return ft.Theme(
        use_material3=True,
        font_family=FONT_FAMILY,
        color_scheme_seed=PRIMARY_COLOR,
        color_scheme=ft.ColorScheme(
            primary=PRIMARY_COLOR, on_primary=CARD_COLOR,
            primary_container=BLUE_SURFACE, on_primary_container=TEXT_COLOR,
            secondary=ACCENT_COLOR, on_secondary=TEXT_COLOR,
            secondary_container=LAVENDER_SURFACE, on_secondary_container=LAVENDER_TEXT,
            surface=CARD_COLOR, on_surface=TEXT_COLOR,
            on_surface_variant=SECONDARY_TEXT_COLOR, surface_container=CARD_COLOR,
            outline=BLUE_BORDER, outline_variant=BLUE_BORDER,
            error=DANGER_COLOR, error_container=DANGER_SURFACE,
        ),
        scaffold_bgcolor=BACKGROUND_COLOR,
        system_overlay_style=ft.SystemOverlayStyle(
            status_bar_color=CARD_COLOR,
            status_bar_icon_brightness=ft.Brightness.DARK,
            status_bar_brightness=ft.Brightness.LIGHT,
            system_navigation_bar_color=CARD_COLOR,
            system_navigation_bar_icon_brightness=ft.Brightness.DARK,
            enforce_system_status_bar_contrast=False,
            enforce_system_navigation_bar_contrast=False,
        ),
        text_theme=ft.TextTheme(
            headline_large=ft.TextStyle(size=HEADLINE_TEXT_SIZE, color=TEXT_COLOR, weight=ft.FontWeight.W_700, font_family=FONT_FAMILY),
            title_large=ft.TextStyle(size=TITLE_TEXT_SIZE, color=TEXT_COLOR, weight=ft.FontWeight.W_700, font_family=FONT_FAMILY),
            title_medium=ft.TextStyle(size=TEXT_SIZE_LARGE, color=TEXT_COLOR, weight=ft.FontWeight.W_700, font_family=FONT_FAMILY),
            body_large=ft.TextStyle(size=TEXT_SIZE_LARGE, color=TEXT_COLOR, font_family=FONT_FAMILY),
            body_medium=ft.TextStyle(size=TEXT_SIZE_MEDIUM, color=SECONDARY_TEXT_COLOR, font_family=FONT_FAMILY),
            body_small=ft.TextStyle(size=TEXT_SIZE_SMALL, color=SECONDARY_TEXT_COLOR, font_family=FONT_FAMILY),
        ),
        dropdown_theme=ft.DropdownTheme(text_style=ft.TextStyle(font_family=FONT_FAMILY)),
        navigation_bar_theme=ft.NavigationBarTheme(
            bgcolor=CARD_COLOR, height=BAR_HEIGHT, elevation=0,
            indicator_color=ft.Colors.TRANSPARENT,
            label_text_style={
                ft.ControlState.DEFAULT: ft.TextStyle(size=TEXT_SIZE_SMALL, color=PRIMARY_COLOR, font_family=FONT_FAMILY),
                ft.ControlState.SELECTED: ft.TextStyle(size=TEXT_SIZE_SMALL, color=PRIMARY_COLOR, weight=ft.FontWeight.W_700, font_family=FONT_FAMILY),
            },
            label_padding=ft.Padding.only(top=0, bottom=NAVIGATION_LABEL_BOTTOM_PADDING),
        ),
        card_theme=ft.CardTheme(color=CARD_COLOR, elevation=0, shape=ft.RoundedRectangleBorder(radius=CARD_RADIUS)),
        chip_theme=ft.ChipTheme(
            bgcolor=LAVENDER_SURFACE, selected_color=ACCENT_COLOR,
            label_text_style=ft.TextStyle(size=TEXT_SIZE_MEDIUM, color=LAVENDER_TEXT, font_family=FONT_FAMILY),
            border_side=ft.BorderSide(0, ft.Colors.TRANSPARENT), shape=ft.StadiumBorder(),
        ),
        filled_button_theme=ft.FilledButtonTheme(style=action_style()),
        outlined_button_theme=ft.OutlinedButtonTheme(style=action_style("tertiary")),
        text_button_theme=ft.TextButtonTheme(style=ft.ButtonStyle(
            color=PRIMARY_COLOR, animation_duration=BUTTON_ANIMATION_DURATION_MS,
            shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS),
            overlay_color={ft.ControlState.PRESSED: ft.Colors.with_opacity(CONTROL_PRESSED_OPACITY, PRIMARY_COLOR)},
        )),
        icon_button_theme=ft.IconButtonTheme(style=ft.ButtonStyle(
            overlay_color={ft.ControlState.PRESSED: ft.Colors.with_opacity(CONTROL_PRESSED_OPACITY, PRIMARY_COLOR)},
        )),
        icon_theme=ft.IconTheme(color=PRIMARY_COLOR, size=ICON_SIZE),
    )
