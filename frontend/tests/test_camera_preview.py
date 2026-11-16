"""Test preview proportions, orientation, and centered cropping."""

from types import SimpleNamespace
from unittest.mock import Mock

import flet as ft
import pytest

from medclue_mobile.ui.camera_preview import fit_camera_preview, preview_aspect_ratio


@pytest.mark.parametrize("width,height,ratio", [
    (280, 210, 3 / 4),
    (280, 210, 16 / 9),
    (280, 210, 4 / 3),
])
def test_preview_covers_the_frame_with_a_centered_crop_without_stretching(width, height, ratio):
    camera = SimpleNamespace(update=Mock())

    fit_camera_preview(camera, width, height, ratio)

    assert camera.width / camera.height == pytest.approx(ratio)
    assert camera.width >= width
    assert camera.height >= height
    assert camera.width == pytest.approx(width) or camera.height == pytest.approx(height)
    assert camera.left * 2 + camera.width == pytest.approx(width)
    assert camera.top * 2 + camera.height == pytest.approx(height)
    camera.update.assert_called_once_with()


@pytest.mark.parametrize("width,height", [(0, 210), (280, 0), (-1, 210), (280, -1)])
def test_preview_waits_for_positive_frame_dimensions(width, height):
    camera = SimpleNamespace(width=None, height=None, update=Mock())

    fit_camera_preview(camera, width, height, 3 / 4)

    assert camera.width is None
    assert camera.height is None
    camera.update.assert_not_called()


@pytest.mark.parametrize("ratio,orientation,expected", [
    (16 / 9, ft.DeviceOrientation.LANDSCAPE_LEFT, 16 / 9),
    (3 / 4, ft.DeviceOrientation.LANDSCAPE_RIGHT, 4 / 3),
    (16 / 9, ft.DeviceOrientation.PORTRAIT_UP, 9 / 16),
    (3 / 4, None, 3 / 4),
])
def test_ratio_matches_the_camera_orientation(ratio, orientation, expected):
    event = SimpleNamespace(
        aspect_ratio=ratio, device_orientation=orientation,
        locked_capture_orientation=None, preview_pause_orientation=None,
    )

    assert preview_aspect_ratio(event) == pytest.approx(expected)


@pytest.mark.parametrize("paused,locked,device,expected", [
    (ft.DeviceOrientation.LANDSCAPE_LEFT, ft.DeviceOrientation.PORTRAIT_UP, ft.DeviceOrientation.PORTRAIT_UP, 16 / 9),
    (ft.DeviceOrientation.PORTRAIT_UP, ft.DeviceOrientation.LANDSCAPE_LEFT, ft.DeviceOrientation.LANDSCAPE_LEFT, 9 / 16),
    (None, ft.DeviceOrientation.LANDSCAPE_LEFT, ft.DeviceOrientation.PORTRAIT_UP, 16 / 9),
])
def test_preview_orientation_takes_priority_over_locked_and_device_orientation(paused, locked, device, expected):
    event = SimpleNamespace(
        aspect_ratio=16 / 9, preview_pause_orientation=paused,
        locked_capture_orientation=locked, device_orientation=device,
    )

    assert preview_aspect_ratio(event) == pytest.approx(expected)


@pytest.mark.parametrize("ratio", [None, 0, -1])
def test_missing_or_invalid_camera_ratio_is_ignored(ratio):
    event = SimpleNamespace(aspect_ratio=ratio)

    assert preview_aspect_ratio(event) is None
