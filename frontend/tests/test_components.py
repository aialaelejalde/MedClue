"""Test shared UI component behavior."""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest

from medclue_mobile.ui.components import DeviceDate, date_label, device_date_locale, stretch_card, text_field, use_chips


ASYNC_OPERATION_TIMEOUT_SECONDS = 5


def test_date_label_refreshes_after_the_device_locale_is_loaded(monkeypatch):
    async def run():
        page = SimpleNamespace(
            get_device_info=AsyncMock(return_value=SimpleNamespace(locales=[ft.Locale("en", "US")])),
            run_task=lambda function: asyncio.create_task(function()),
        )
        monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
        label = DeviceDate(date(2026, 11, 15))
        label.update = Mock()
        assert label.value == "2026-11-15"

        label.did_mount()
        await asyncio.wait_for(label._format_task, timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)

        assert label.value == "11/15/26"
        page.get_device_info.assert_awaited_once_with()
        label.update.assert_called_once_with()

    asyncio.run(run())


def test_tapping_outside_a_text_field_requests_blur_and_preserves_input(monkeypatch):
    field = text_field(value="Keep this input")
    field.update = Mock()
    monkeypatch.setattr(ft.Control, "parent", property(lambda self: object()))
    original_blur = field.blur

    field.on_tap_outside(None)

    assert field.blur != original_blur
    assert field.value == "Keep this input"
    field.update.assert_called_once_with()


@pytest.mark.parametrize("center_information", [False, True])
def test_result_card_reflows_when_the_available_height_changes(center_information):
    information, actions, leading = ft.Column(), ft.Column(), ft.Container()
    card = ft.Container(ft.Column([information, actions], spacing=16))
    resize = stretch_card(card, leading, center_information=center_information)
    information.on_size_change(SimpleNamespace(height=100))
    actions.on_size_change(SimpleNamespace(height=50))
    resize(SimpleNamespace(height=800))
    assert card.content.controls[0].padding is None

    leading.on_size_change(SimpleNamespace(height=100))
    padding = card.content.controls[0].padding
    assert padding.bottom > 0
    assert padding.top == (padding.bottom if center_information else 0)

    resize(SimpleNamespace(height=80))
    padding = card.content.controls[0].padding
    assert padding.top == padding.bottom == 0
    assert card.content.controls[0].content is information
    assert card.content.controls[1] is actions


def test_compact_use_summary_keeps_full_text_available_without_changing_original_uses():
    uses = ["Moderate pain (including migraine; age 14+)", "Fever (short term (adults only))", "(Restriction only)"]
    original_uses = list(uses)
    summary = use_chips(uses, compact=True)
    first, second, counter = summary.content.controls
    assert [first.content.value, second.content.value] == ["Moderate pain", "Fever"]
    assert [first.tooltip, second.tooltip] == uses[:2]

    first.on_size_change(SimpleNamespace(width=120))
    second.on_size_change(SimpleNamespace(width=70))
    counter.on_size_change(SimpleNamespace(width=20))
    summary.on_size_change(SimpleNamespace(width=150))

    visible_use, overflow = summary.content.controls
    assert visible_use.content.value == "Moderate pain"
    assert visible_use.tooltip == uses[0]
    assert overflow.value == "+2"
    assert overflow.tooltip == "\n".join(uses[1:])
    assert uses == original_uses


@pytest.mark.parametrize("locale,expected", [
    (ft.Locale("en", "GB"), "15/11/2026"),
    (ft.Locale("en", "US"), "11/15/26"),
    (None, "2026-11-15"),
    (ft.Locale("unknown"), "2026-11-15"),
])
def test_date_uses_regional_format_or_iso_when_no_valid_locale_is_available(locale, expected):
    assert date_label(date(2026, 11, 15), locale) == expected


@pytest.mark.parametrize("device,expected", [
    (SimpleNamespace(locales=[ft.Locale("en", "GB"), ft.Locale("en", "US")]), ft.Locale("en", "GB")),
    (SimpleNamespace(locales=[]), None),
    (None, None),
])
def test_device_date_locale_uses_the_first_available_locale(device, expected):
    page = SimpleNamespace(get_device_info=AsyncMock(return_value=device))

    assert asyncio.run(device_date_locale(page)) == expected


def test_device_locale_failure_allows_the_iso_fallback():
    page = SimpleNamespace(get_device_info=AsyncMock(side_effect=ft.FletException()))

    assert asyncio.run(device_date_locale(page)) is None


def test_unmounting_a_date_cancels_its_pending_device_lookup(monkeypatch):
    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def get_device_info():
            started.set()
            await release.wait()

        page = SimpleNamespace(
            get_device_info=AsyncMock(side_effect=get_device_info),
            run_task=lambda function: asyncio.create_task(function()),
        )
        monkeypatch.setattr(ft.Control, "page", property(lambda self: page))
        label = DeviceDate(date(2026, 11, 15))
        label.update = Mock()
        label.did_mount()
        try:
            await asyncio.wait_for(started.wait(), timeout=ASYNC_OPERATION_TIMEOUT_SECONDS)
        finally:
            label.will_unmount()
            with pytest.raises(asyncio.CancelledError):
                await label._format_task
        label.update.assert_not_called()

    asyncio.run(run())
