"""Manage the camera, temporary photos, and photo compression for saving."""

import asyncio
from io import BytesIO

import flet_camera as fc
import flet_permission_handler as fph
from PIL import Image, ImageOps, UnidentifiedImageError

from medclue_mobile.api_client import MAX_PHOTO_BYTES, PhotoTooLargeError


STORED_PHOTO_MAX_SIDE = 1600
STORED_PHOTO_JPEG_QUALITY = 85
IMAGE_MEDIA_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class CameraPermissionError(PermissionError):
    pass


class PhotoManager:
    """Keep captured photos in memory until the user saves or discards them."""

    def __init__(self):
        self.camera = fc.Camera(expand=True)
        self._permissions = fph.PermissionHandler()
        self._photo: bytes | None = None
        self._media_type: str | None = None
        self._camera_ready = False
        self._capture_id = 0

    @property
    def photo(self) -> bytes | None:
        return self._photo

    @property
    def media_type(self) -> str | None:
        return self._media_type

    async def initialize_camera(self) -> None:
        self._camera_ready = False
        status = await self._permissions.get_status(fph.Permission.CAMERA)
        if status not in (
            fph.PermissionStatus.GRANTED,
            fph.PermissionStatus.PERMANENTLY_DENIED,
            fph.PermissionStatus.RESTRICTED,
        ):
            status = await self._permissions.request(fph.Permission.CAMERA)
        if status != fph.PermissionStatus.GRANTED:
            raise CameraPermissionError("Allow camera access in Settings to take photos.")

        cameras = await self.camera.get_available_cameras()
        if not cameras:
            raise RuntimeError("No camera is available on this device.")
        selected = next(
            (camera for camera in cameras if camera.lens_direction == fc.CameraLensDirection.BACK),
            cameras[0],
        )
        await self.camera.initialize(
            description=selected,
            resolution_preset=fc.ResolutionPreset.MAX,
            enable_audio=False,
            image_format_group=fc.ImageFormatGroup.JPEG,
        )
        self._camera_ready = True

    async def capture(self, *, for_identification: bool = False) -> bytes:
        if for_identification:
            self.discard_photo()
        if not self._camera_ready:
            raise RuntimeError("Initialize the camera before taking a photo.")
        self._capture_id += 1
        capture_id = self._capture_id
        photo = await self.camera.take_picture()
        if capture_id != self._capture_id:
            raise asyncio.CancelledError()
        if not isinstance(photo, bytes) or not photo:
            raise ValueError("The photo must contain image bytes.")
        if for_identification and len(photo) > MAX_PHOTO_BYTES:
            raise PhotoTooLargeError("The photo is too large.")
        try:
            with Image.open(BytesIO(photo)) as image:
                media_type = IMAGE_MEDIA_TYPES.get(image.format)
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("The captured photo could not be read.") from error
        if media_type is None:
            raise ValueError("The photo must use JPEG, PNG, or WebP format.")

        self._photo = photo
        self._media_type = media_type
        return photo

    def discard_photo(self) -> None:
        """Clear the photo and ignore any capture already in progress."""
        self._capture_id += 1
        self._photo = None
        self._media_type = None


def compress_photo(photo: bytes) -> bytes:
    """Create a smaller JPEG for SQLite without changing the original photo bytes."""
    if not isinstance(photo, bytes) or not photo:
        raise ValueError("The photo must contain image bytes.")
    try:
        with Image.open(BytesIO(photo)) as source:
            if source.format not in IMAGE_MEDIA_TYPES:
                raise ValueError("The photo must use JPEG, PNG, or WebP format.")
            image = ImageOps.exif_transpose(source)
            image.thumbnail(
                (STORED_PHOTO_MAX_SIDE, STORED_PHOTO_MAX_SIDE), Image.Resampling.LANCZOS
            )
            if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image = image.convert("RGB")
            output = BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=STORED_PHOTO_JPEG_QUALITY,
                optimize=True,
                icc_profile=source.info.get("icc_profile"),
            )
            return output.getvalue()
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("The photo could not be prepared for saving.") from error
