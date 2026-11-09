"""Test camera handling with simulated controls and real in-memory image compression."""

import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import flet_camera as fc
import flet_permission_handler as fph
import pytest
from PIL import Image

from medclue_mobile.api_client import MAX_PHOTO_BYTES, PhotoTooLargeError
from medclue_mobile.photos import CameraPermissionError, PhotoManager, compress_photo


def make_photo(size=(80, 40)):
    output = BytesIO()
    with Image.new("RGB", size, (100, 150, 200)) as image:
        image.save(output, format="JPEG")
    return output.getvalue()


@pytest.fixture
def photos(monkeypatch):
    front = fc.CameraDescription(name="front", lens_direction=fc.CameraLensDirection.FRONT, sensor_orientation=0)
    back = fc.CameraDescription(name="back", lens_direction=fc.CameraLensDirection.BACK, sensor_orientation=90)
    camera = SimpleNamespace(
        get_available_cameras=AsyncMock(return_value=[front, back]),
        initialize=AsyncMock(),
        take_picture=AsyncMock(return_value=make_photo()),
    )
    permissions = SimpleNamespace(
        get_status=AsyncMock(return_value=fph.PermissionStatus.GRANTED),
        request=AsyncMock(return_value=fph.PermissionStatus.GRANTED),
        open_app_settings=AsyncMock(return_value=True),
    )
    monkeypatch.setattr("medclue_mobile.photos.fc.Camera", Mock(return_value=camera))
    monkeypatch.setattr("medclue_mobile.photos.fph.PermissionHandler", Mock(return_value=permissions))
    return SimpleNamespace(manager=PhotoManager(), camera=camera, permissions=permissions, back=back)


def test_initialization_selects_the_back_camera_without_audio(photos):
    asyncio.run(photos.manager.initialize_camera())

    photos.permissions.get_status.assert_awaited_once_with(fph.Permission.CAMERA)
    photos.permissions.request.assert_not_awaited()
    photos.camera.initialize.assert_awaited_once_with(
        description=photos.back,
        resolution_preset=fc.ResolutionPreset.MAX,
        enable_audio=False,
        image_format_group=fc.ImageFormatGroup.JPEG,
    )


def test_permission_is_requested_when_not_already_granted(photos):
    photos.permissions.get_status.return_value = fph.PermissionStatus.DENIED

    asyncio.run(photos.manager.initialize_camera())

    photos.permissions.request.assert_awaited_once_with(fph.Permission.CAMERA)
    photos.camera.initialize.assert_awaited_once()


@pytest.mark.parametrize("status", [fph.PermissionStatus.DENIED, fph.PermissionStatus.PERMANENTLY_DENIED])
def test_denied_permission_prevents_camera_initialization(photos, status):
    photos.permissions.get_status.return_value = status
    photos.permissions.request.return_value = status

    with pytest.raises(CameraPermissionError):
        asyncio.run(photos.manager.initialize_camera())

    photos.camera.get_available_cameras.assert_not_awaited()
    photos.camera.initialize.assert_not_awaited()
    if status == fph.PermissionStatus.PERMANENTLY_DENIED:
        photos.permissions.request.assert_not_awaited()


def test_no_available_camera_produces_a_clear_error(photos):
    photos.camera.get_available_cameras.return_value = []

    with pytest.raises(RuntimeError, match="No camera is available"):
        asyncio.run(photos.manager.initialize_camera())

    photos.camera.initialize.assert_not_awaited()


def test_capture_keeps_original_bytes_and_discard_clears_them(photos):
    original = photos.camera.take_picture.return_value
    asyncio.run(photos.manager.initialize_camera())

    result = asyncio.run(photos.manager.capture(for_identification=True))

    assert result is original
    assert photos.manager.photo is original
    assert photos.manager.media_type == "image/jpeg"
    photos.manager.discard_photo()
    assert photos.manager.photo is None
    assert photos.manager.media_type is None


@pytest.mark.parametrize("for_identification", [False, True])
def test_large_photo_limit_applies_only_to_identification(photos, for_identification):
    asyncio.run(photos.manager.initialize_camera())
    previous = asyncio.run(photos.manager.capture())
    large_photo = previous + b"x" * (MAX_PHOTO_BYTES + 1 - len(previous))
    photos.camera.take_picture.return_value = large_photo

    if for_identification:
        with pytest.raises(PhotoTooLargeError):
            asyncio.run(photos.manager.capture(for_identification=True))
        assert photos.manager.photo is None
        assert photos.manager.media_type is None
    else:
        assert asyncio.run(photos.manager.capture()) is large_photo


def test_identification_clears_previous_photo_before_capture_starts(photos):
    asyncio.run(photos.manager.initialize_camera())
    asyncio.run(photos.manager.capture())

    async def failed_capture():
        assert photos.manager.photo is None
        assert photos.manager.media_type is None
        raise RuntimeError("Capture failed")

    photos.camera.take_picture.side_effect = failed_capture
    with pytest.raises(RuntimeError, match="Capture failed"):
        asyncio.run(photos.manager.capture(for_identification=True))

    assert photos.manager.photo is None
    assert photos.manager.media_type is None


def test_capture_requires_camera_initialization(photos):
    with pytest.raises(RuntimeError, match="Initialize the camera"):
        asyncio.run(photos.manager.capture())

    photos.camera.take_picture.assert_not_awaited()


@pytest.mark.parametrize("photo", [b"", b"not an image"])
def test_invalid_capture_keeps_the_previous_photo(photos, photo):
    asyncio.run(photos.manager.initialize_camera())
    previous = asyncio.run(photos.manager.capture())
    photos.camera.take_picture.return_value = photo

    with pytest.raises(ValueError):
        asyncio.run(photos.manager.capture())

    assert photos.manager.photo is previous


def test_discard_ignores_a_capture_that_returns_later(photos):
    async def capture_and_discard():
        await photos.manager.initialize_camera()
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_capture():
            started.set()
            await release.wait()
            return make_photo()

        photos.camera.take_picture.side_effect = delayed_capture
        task = asyncio.create_task(photos.manager.capture())
        await asyncio.wait_for(started.wait(), timeout=1)
        photos.manager.discard_photo()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(capture_and_discard())
    assert photos.manager.photo is None
    assert photos.manager.media_type is None


def test_compression_reduces_size_without_changing_the_captured_original(photos):
    original = make_photo((3200, 1600))
    photos.camera.take_picture.return_value = original
    asyncio.run(photos.manager.initialize_camera())
    asyncio.run(photos.manager.capture())

    compressed = compress_photo(photos.manager.photo)

    assert photos.manager.photo is original
    assert len(compressed) < len(original)
    with Image.open(BytesIO(compressed)) as image:
        assert image.format == "JPEG"
        assert image.size == (1600, 800)
        assert image.mode == "RGB"
        assert all(abs(value - expected) <= 5 for value, expected in zip(image.getpixel((0, 0)), (100, 150, 200)))


def test_compression_corrects_orientation_without_enlarging_and_removes_exif():
    output = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "Camera owner"
    with Image.new("RGB", (80, 40), "blue") as image:
        image.save(output, format="JPEG", exif=exif)
    original = output.getvalue()

    compressed = compress_photo(original)

    with Image.open(BytesIO(compressed)) as image:
        assert image.size == (40, 80)
        assert not image.getexif()
    with Image.open(BytesIO(original)) as image:
        assert image.size == (80, 40)
        assert image.getexif()[274] == 6


@pytest.mark.parametrize("photo", [b"", b"not an image"])
def test_invalid_photo_cannot_be_compressed(photo):
    with pytest.raises(ValueError):
        compress_photo(photo)
