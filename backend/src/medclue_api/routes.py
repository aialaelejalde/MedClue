"""Receive identify and verify requests and return JSON results."""

import asyncio
from collections.abc import Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from medclue_api.identification import IdentificationService
from medclue_api.schemas import IdentificationResponse, VerifyRequest


MAX_PHOTO_BYTES = 15 * 1024 * 1024

router = APIRouter()


async def get_identification_service(request: Request) -> IdentificationService:
    service = getattr(request.app.state, "identification_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="The identification service is not available.")
    return service


@router.post("/identify", response_model=IdentificationResponse)
async def identify(
    request: Request,
    photo: Annotated[UploadFile, File()],
    service: Annotated[IdentificationService, Depends(get_identification_service)],
) -> IdentificationResponse:
    try:
        if photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise HTTPException(status_code=415, detail="The photo must use JPEG, PNG, or WebP format.")
        image = await photo.read(MAX_PHOTO_BYTES + 1)
        if len(image) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="The photo is too large.")
        if not image:
            raise HTTPException(status_code=400, detail="The photo must contain image bytes.")

        return await _run_until_disconnected(request, service.identify(image, photo.content_type))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        await photo.close()


@router.post("/verify", response_model=IdentificationResponse)
async def verify(
    request: Request,
    selection: VerifyRequest,
    service: Annotated[IdentificationService, Depends(get_identification_service)],
) -> IdentificationResponse:
    try:
        return await _run_until_disconnected(request, service.verify(selection))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


async def _run_until_disconnected(request: Request, operation: Coroutine[Any, Any, IdentificationResponse]) -> IdentificationResponse:
    """Stop identification if the client disconnects or the task is cancelled."""
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            if await request.is_disconnected():
                raise HTTPException(status_code=499, detail="Identification cancelled.")
            await asyncio.wait({task}, timeout=0.1)
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
