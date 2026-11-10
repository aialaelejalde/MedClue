"""Show confirmation and error dialogs."""

import asyncio

import flet as ft

from medclue_mobile.ui.theme import ACCENT_COLOR, BACKGROUND_COLOR, CARD_RADIUS, CARD_SPACING


async def confirm_duplicate(page: ft.Page) -> bool:
    return await _show_dialog(
        page,
        "Possible duplicate",
        "You already have a medication with this name in your medicine cabinet. "
        "Would you like to save another entry?",
        action_text="Save anyway",
        cancel_text="Continue editing",
    )


async def confirm_discard_changes(page: ft.Page) -> bool:
    return await _show_dialog(
        page,
        "Discard changes?",
        "You have unsaved changes to this medication.",
        action_text="Discard changes",
        cancel_text="Keep editing",
    )


async def confirm_delete_medication(page: ft.Page) -> bool:
    return await _show_dialog(
        page,
        "Delete medication?",
        "Are you sure you want to delete this medication from your medicine cabinet? "
        "This action cannot be undone.",
        action_text="Delete",
        cancel_text="Cancel",
    )


async def confirm_leave_identification(page: ft.Page) -> bool:
    return await _show_dialog(
        page,
        "Leave identification?",
        "Your medication is still being identified. Leaving now will cancel the process.",
        action_text="Cancel & leave",
        cancel_text="Keep identifying",
    )


async def show_error(
    page: ft.Page,
    title: str,
    message: str,
    *,
    action_text: str = "OK",
) -> bool:
    """Return True only when the user presses the error dialog's action."""
    return await _show_dialog(page, title, message, action_text=action_text)


async def show_empty_record_error(page: ft.Page) -> None:
    await show_error(
        page,
        "Cannot save medication",
        "Please add at least one piece of information before saving.",
    )


async def show_photo_too_large(page: ft.Page) -> bool:
    return await show_error(
        page,
        "Photo is too large",
        "This photo is over 15 MB. Please take another photo.",
        action_text="Retake photo",
    )


def show_save_success(page: ft.Page) -> None:
    page.show_dialog(ft.SnackBar(
        content=ft.Text("Medication saved successfully", color=BACKGROUND_COLOR),
        bgcolor=ACCENT_COLOR,
    ))


async def _show_dialog(
    page: ft.Page,
    title: str,
    message: str,
    *,
    action_text: str,
    cancel_text: str | None = None,
) -> bool:
    """Handle dialog choices and close it on cancellation."""
    result = asyncio.get_running_loop().create_future()

    def choose(value: bool) -> None:
        if not result.done():
            result.set_result(value)
            if dialog.open:
                page.pop_dialog()

    def dismiss(event: ft.Event) -> None:
        dialog.open = False
        choose(False)

    actions = []
    if cancel_text is not None:
        actions.append(ft.TextButton(cancel_text, on_click=lambda: choose(False)))
    actions.append(ft.TextButton(action_text, on_click=lambda: choose(True)))

    dialog = ft.AlertDialog(
        title=ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_LARGE),
        content=ft.Text(message, theme_style=ft.TextThemeStyle.BODY_LARGE),
        actions=actions,
        on_dismiss=dismiss,
        modal=False,
        scrollable=True,
        bgcolor=BACKGROUND_COLOR,
        shape=ft.RoundedRectangleBorder(radius=CARD_RADIUS),
        actions_overflow_button_spacing=CARD_SPACING,
    )
    page.show_dialog(dialog)
    try:
        return await result
    finally:
        if dialog.open:
            page.pop_dialog()
