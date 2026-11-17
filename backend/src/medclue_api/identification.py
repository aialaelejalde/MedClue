"""Manage medication identification, verification, and error handling."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

import httpx
from openai import OpenAIError

from medclue_api.cima_client import CimaClient, normalize_national_code
from medclue_api.config import IDENTIFICATION_TIMEOUT_SECONDS
from medclue_api.matching import compare_presentation, find_presentation_matches
from medclue_api.official_uses import OfficialUsesProcessor
from medclue_api.openai_client import OpenAIClient
from medclue_api.retry_tokens import RetryState, RetryTokenManager
from medclue_api.schemas import (CimaPresentation, IdentificationResponse, MedicationCandidate, ProcessingStep, VerifyRequest)


logger = logging.getLogger(__name__)


@dataclass
class _IdentificationProgress:
    current_step: ProcessingStep = "image_analysis"
    candidate: MedicationCandidate | None = None
    national_code: str | None = None
    medication: CimaPresentation | None = None
    uses_processor: OfficialUsesProcessor | None = None


class IdentificationService:
    def __init__(self, cima_client: CimaClient, openai_client: OpenAIClient, token_manager: RetryTokenManager):
        self._cima_client = cima_client
        self._openai_client = openai_client
        self._token_manager = token_manager

    async def identify(self, photo: bytes, media_type: str = "image/jpeg") -> IdentificationResponse:
        if not isinstance(photo, bytes) or not photo:
            raise ValueError("The photo must contain image bytes.")
        if media_type not in ("image/jpeg", "image/png", "image/webp"):
            raise ValueError("The photo must use JPEG, PNG, or WebP format.")

        return await self._run(_IdentificationProgress(), photo, media_type)

    async def process_selection_or_retry(self, request: VerifyRequest) -> IdentificationResponse:
        """Process a user selection or resume a signed retry without image analysis."""
        if request.retry_token is not None:
            state = self._token_manager.read_token(request.retry_token)
            progress = _IdentificationProgress(
                current_step=state.failed_step,
                candidate=state.candidate,
                national_code=state.national_code,
                medication=state.medication,
            )
            if state.medication is not None:
                progress.uses_processor = OfficialUsesProcessor(
                    state.medication,
                    self._cima_client,
                    self._openai_client,
                    indications=state.indications,
                )
        else:
            progress = _IdentificationProgress(
                current_step="cima_verification",
                candidate=request.candidate,
                national_code=request.national_code,
            )

        return await self._run(progress)

    async def _run(self, progress: _IdentificationProgress, photo: bytes | None = None, media_type: str = "image/jpeg") -> IdentificationResponse:
        try:
            return await asyncio.wait_for(
                self._process(progress, photo, media_type),
                timeout=IDENTIFICATION_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            return self._failure_response(progress, "timeout")
        except (httpx.HTTPError, OpenAIError, ValueError) as error:
            logger.warning("Identification step failed", extra={
                "step": progress.uses_processor.current_step if progress.uses_processor else progress.current_step,
                "error_type": type(error).__name__,
            })
            return self._failure_response(progress, "connection_error")

    async def _process(self, progress: _IdentificationProgress, photo: bytes | None, media_type: str) -> IdentificationResponse:
        if photo is not None:
            analysis = await self._openai_client.analyze_image(photo, media_type)
            if not analysis.candidates:
                return IdentificationResponse(status="not_identified")
            if len(analysis.candidates) > 1:
                return IdentificationResponse(status="multiple_matches", candidates=analysis.candidates)
            progress.candidate = analysis.candidates[0]
            progress.current_step = "cima_verification"

        if progress.medication is None:
            if progress.national_code is not None:
                progress.medication = await self._cima_client.get_presentation(progress.national_code)
                if progress.medication is None:
                    raise LookupError("The selected CIMA presentation was not found.")
            elif progress.candidate is not None:
                national_code = normalize_national_code(progress.candidate.national_code)
                if national_code is not None:
                    presentation = await self._cima_client.get_presentation(national_code)
                    if presentation is not None:
                        if compare_presentation(progress.candidate, presentation, require_complete_details=False) is not True:
                            return IdentificationResponse(status="no_match", suggested_candidate=progress.candidate)
                        progress.medication = presentation

                if progress.medication is None:
                    presentations = await self._cima_client.search_presentations(progress.candidate.name)
                    matches = find_presentation_matches(progress.candidate, presentations)
                    if matches.verified is None:
                        if len(matches.presentations) > 1:
                            return IdentificationResponse(
                                status="multiple_matches",
                                suggested_candidate=progress.candidate,
                                presentations=matches.presentations,
                            )
                        return IdentificationResponse(status="no_match", suggested_candidate=progress.candidate)
                    progress.medication = matches.verified
            else:
                raise ValueError("A candidate or national code is required for verification.")

        if progress.uses_processor is None:
            progress.uses_processor = OfficialUsesProcessor(
                progress.medication, self._cima_client, self._openai_client
            )

        uses = await progress.uses_processor.get_and_translate_uses()

        return IdentificationResponse(status="verified", medication=progress.medication, official_uses=uses)

    def _failure_response(self, progress: _IdentificationProgress, status: Literal["connection_error", "timeout"]) -> IdentificationResponse:
        step = progress.current_step
        token = None
        suggested_candidate = progress.candidate
        if progress.uses_processor is not None:
            step = progress.uses_processor.current_step
            state = RetryState(
                failed_step=step,
                medication=progress.medication,
                indications=progress.uses_processor.indications,
            )
            token = self._token_manager.create_token(state)
            return IdentificationResponse(
                status="verified",
                medication=progress.medication,
                failed_step=step,
                retry_token=token,
            )
        elif step == "cima_verification":
            state = RetryState(
                failed_step="cima_verification",
                candidate=progress.candidate,
                national_code=progress.national_code,
            )
            token = self._token_manager.create_token(state)

        return IdentificationResponse(
            status=status,
            suggested_candidate=suggested_candidate,
            failed_step=step,
            retry_token=token,
        )
