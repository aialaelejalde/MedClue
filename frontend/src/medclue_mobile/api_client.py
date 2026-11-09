"""Send photos and selected candidates to the backend."""

import asyncio

import httpx


IDENTIFICATION_TIMEOUT_SECONDS = 45
MAX_PHOTO_BYTES = 15 * 1024 * 1024
IDENTIFICATION_STATUSES = (
    "verified", "multiple_matches", "not_identified",
    "no_match", "connection_error", "timeout",
)


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiConnectionError(ApiError):
    pass


class ApiTimeoutError(ApiError):
    pass


class PhotoTooLargeError(ApiError):
    pass


class MedClueApiClient:
    def __init__(self, backend_url: str):
        url = httpx.URL(backend_url)
        if url.scheme != "https" or not url.host:
            raise ValueError("The backend URL must use HTTPS and include a host.")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("The backend URL cannot include credentials, a query, or a fragment.")
        self._client = httpx.AsyncClient(
            base_url=url,
            timeout=IDENTIFICATION_TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )

    async def identify(self, photo: bytes, media_type: str = "image/jpeg") -> dict:
        if not isinstance(photo, bytes) or not photo:
            raise ValueError("The photo must contain image bytes.")
        if media_type not in ("image/jpeg", "image/png", "image/webp"):
            raise ValueError("The photo must use JPEG, PNG, or WebP format.")
        if len(photo) > MAX_PHOTO_BYTES:
            raise PhotoTooLargeError("The photo is too large.")

        return await self._post("identify", files={"photo": ("package", photo, media_type)})

    async def verify(self, *, candidate: dict | None = None, national_code: str | None = None, retry_token: str | None = None) -> dict:
        selection = {
            key: value
            for key, value in (
                ("candidate", candidate), ("national_code", national_code), ("retry_token", retry_token)
            )
            if value is not None
        }
        if len(selection) != 1:
            raise ValueError("Send one candidate, national code, or retry token.")
        if candidate is not None:
            if not isinstance(candidate, dict) or set(candidate) != {"name", "strength", "form"}:
                raise ValueError("A candidate must contain only name, strength, and form.")
            if not isinstance(candidate["name"], str) or not candidate["name"].strip():
                raise ValueError("The candidate name must contain text.")
            for value in candidate.values():
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    raise ValueError("Candidate fields must contain text or null.")
        else:
            value = national_code if national_code is not None else retry_token
            if not isinstance(value, str) or not value.strip():
                raise ValueError("The national code or retry token must contain text.")

        return await self._post("verify", json=selection)

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, **kwargs) -> dict:
        try:
            response = await asyncio.wait_for(
                self._client.post(path, **kwargs), timeout=IDENTIFICATION_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError as error:
            raise ApiTimeoutError("The identification request took too long.") from error
        except httpx.RequestError as error:
            raise ApiConnectionError("Could not connect to the identification service.") from error

        if not response.is_success:
            message = "The backend could not complete the request."
            try:
                data = response.json()
                if isinstance(data, dict) and isinstance(data.get("detail"), str) and data["detail"].strip():
                    message = data["detail"]
            except ValueError:
                pass
            if path == "identify" and response.status_code == 413:
                raise PhotoTooLargeError(message, status_code=413)
            raise ApiError(message, status_code=response.status_code)

        try:
            result = response.json()
        except ValueError as error:
            raise ApiError("The backend returned an invalid response.") from error
        if not isinstance(result, dict) or result.get("status") not in IDENTIFICATION_STATUSES:
            raise ApiError("The backend returned an invalid response.")
        return result
