"""Fit camera previews to their frames while preserving image proportions."""

import flet as ft
from flet_camera import CameraStateEvent


DEFAULT_PREVIEW_ASPECT_RATIO = 3 / 4


def preview_aspect_ratio(event: CameraStateEvent) -> float | None:
    """Return the camera preview aspect ratio adjusted for orientation."""
    ratio = event.aspect_ratio
    if ratio is None or ratio <= 0:
        return None
    orientation = event.preview_pause_orientation or event.locked_capture_orientation or event.device_orientation
    landscape = orientation in (ft.DeviceOrientation.LANDSCAPE_LEFT, ft.DeviceOrientation.LANDSCAPE_RIGHT)
    return max(ratio, 1 / ratio) if landscape else min(ratio, 1 / ratio)


def fit_camera_preview(camera: ft.LayoutControl, width: float, height: float, aspect_ratio: float) -> None:
    """Size and center the camera preview to fill its frame without distortion."""
    if width <= 0 or height <= 0:
        return
    camera.width = max(width, height * aspect_ratio)
    camera.height = camera.width / aspect_ratio
    camera.left = (width - camera.width) / 2
    camera.top = (height - camera.height) / 2
    camera.update()
