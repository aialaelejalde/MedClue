"""Manage the current identification attempt, retries, and cancellation."""

import asyncio
from copy import deepcopy

from medclue_mobile.api_client import (
    ApiConnectionError,
    ApiError,
    ApiTimeoutError,
    MedClueApiClient,
)


class IdentificationSession:
    def __init__(self, api_client: MedClueApiClient):
        self._api_client = api_client
        self._photo: bytes | None = None
        self._media_type: str | None = None
        self._result: dict | None = None
        self._selection: dict | None = None
        self._task: asyncio.Task | None = None
        self._request_id = 0

    @property
    def photo(self) -> bytes | None:
        return self._photo

    @property
    def media_type(self) -> str | None:
        return self._media_type

    @property
    def result(self) -> dict | None:
        return deepcopy(self._result)

    @property
    def is_running(self) -> bool:
        return self._task is not None

    @property
    def can_retry(self) -> bool:
        return (
            not self.is_running
            and self._result is not None
            and (
                self._result.get("status") in ("not_identified", "connection_error", "timeout")
                or (
                    self._result.get("status") == "verified"
                    and self._result.get("failed_step") in ("official_uses_retrieval", "uses_translation")
                    and bool(self._result.get("retry_token"))
                )
            )
        )

    async def identify(self, photo: bytes, media_type: str = "image/jpeg") -> dict:
        """Start a fresh attempt and discard any previous result."""
        self.cancel()
        self._photo = photo
        self._media_type = media_type
        return await self._run(None)

    async def select_match(self, index: int) -> dict:
        """Verify the selected AI candidate or CIMA presentation."""
        if self.is_running:
            raise ValueError("Identification is already running.")
        if self._result is None or self._result.get("status") != "multiple_matches":
            raise ValueError("There are no possible matches to select.")

        candidates = self._result.get("candidates") or []
        presentations = self._result.get("presentations") or []
        options = candidates or presentations
        if type(index) is not int or not 0 <= index < len(options):
            raise ValueError("Select a valid possible match.")

        option = options[index]
        candidate = {key: option.get(key) for key in ("name", "strength", "form")}
        selection = (
            {"candidate": candidate}
            if candidates else {"national_code": option["national_code"]}
        )
        return await self._run(selection, candidate)

    async def retry(self) -> dict:
        if not self.can_retry:
            raise ValueError("There is no failed identification to retry.")
        candidate = self._result.get("suggested_candidate")
        return await self._run(self._selection, candidate)

    def cancel(self) -> None:
        """Clear the session immediately and reject results from older requests."""
        self._request_id += 1
        if self._task is not None:
            self._task.cancel()
        self._task = None
        self._photo = None
        self._media_type = None
        self._result = None
        self._selection = None

    async def _run(self, selection: dict | None, candidate: dict | None = None) -> dict:
        """Execute an identification request and manage its result, errors, and cancellation."""
        self._request_id += 1
        request_id = self._request_id
        previous_result = self._result or {}
        self._result = None
        self._selection = deepcopy(selection)
        operation = (
            self._api_client.identify(self._photo, self._media_type)
            if selection is None else self._api_client.send_selection_or_retry(**deepcopy(selection))
        )
        task = asyncio.create_task(operation)
        self._task = task

        try:
            try:
                result = deepcopy(await task)
                if request_id != self._request_id:
                    raise asyncio.CancelledError()

                if result.get("status") in ("connection_error", "timeout") or (
                    result.get("status") == "verified" and result.get("failed_step") is not None
                ):
                    if result.get("status") != "verified" and result.get("suggested_candidate") is None and candidate is not None:
                        result["suggested_candidate"] = deepcopy(candidate)
                    token = result.get("retry_token")
                    if token:
                        self._selection = {"retry_token": token}
                    elif result.get("failed_step") == "image_analysis":
                        self._selection = None
                    else:
                        raise ApiError("The backend did not return the data needed to retry.")
            except ApiError as error:
                if not (
                    isinstance(error, (ApiConnectionError, ApiTimeoutError))
                    or (error.status_code is not None and 500 <= error.status_code < 600)
                ):
                    raise
                result = {
                    "status": "timeout" if isinstance(error, ApiTimeoutError) else "connection_error",
                    "suggested_candidate": deepcopy(candidate),
                    "failed_step": previous_result.get("failed_step") or (
                        "image_analysis" if selection is None else "cima_verification"
                    ),
                    "retry_token": selection.get("retry_token") if selection else None,
                }
                if previous_result.get("status") == "verified":
                    result = deepcopy(previous_result)

            if request_id != self._request_id:
                raise asyncio.CancelledError()

            self._result = deepcopy(result)
            return deepcopy(result)
        except asyncio.CancelledError:
            if request_id == self._request_id:
                self.cancel()
            raise
        except Exception:
            if request_id != self._request_id:
                raise asyncio.CancelledError() from None
            raise
        finally:
            if request_id == self._request_id:
                self._task = None
