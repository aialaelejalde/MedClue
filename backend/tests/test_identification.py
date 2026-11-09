"""Test identification, retries, cancellation, and the 40-second processing limit."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError

from medclue_api.identification import IDENTIFICATION_TIMEOUT_SECONDS, IdentificationService
from medclue_api.retry_tokens import RetryTokenManager
from medclue_api.schemas import (CimaPresentation, ImageAnalysisResult, MedicationCandidate, OfficialUsesResult, VerifyRequest)


TEST_SECRET = "test-retry-secret-with-at-least-32-characters"


@pytest.fixture
def identification():
    candidate = MedicationCandidate(name="Example", strength="500 mg", form="tablet")
    medication = CimaPresentation(
        name="EXAMPLE 500 mg COMPRIMIDOS",
        strength="500 mg",
        form="comprimido",
        registration_number="000001",
        national_code="000010",
    )
    cima = SimpleNamespace(
        search_presentations=AsyncMock(return_value=[medication]),
        get_presentation=AsyncMock(return_value=medication),
        get_official_indications=AsyncMock(return_value="Official indications"),
    )
    openai = SimpleNamespace(
        analyze_image=AsyncMock(return_value=ImageAnalysisResult(candidates=[candidate])),
        translate_official_uses=AsyncMock(
            return_value=OfficialUsesResult(official_uses=["Supported use"])
        ),
    )
    tokens = RetryTokenManager(TEST_SECRET)
    return SimpleNamespace(
        service=IdentificationService(cima, openai, tokens),
        cima=cima, openai=openai, tokens=tokens,
        candidate=candidate, medication=medication,
    )


def processing_calls(context):
    return {
        "image_analysis": context.openai.analyze_image,
        "cima_verification": context.cima.search_presentations,
        "official_uses_retrieval": context.cima.get_official_indications,
        "uses_translation": context.openai.translate_official_uses,
    }


def test_single_candidate_returns_verified_medication_and_uses(identification):
    context = identification

    result = asyncio.run(context.service.identify(b"package photo", "image/png"))

    assert result.status == "verified"
    assert result.medication == context.medication
    assert result.official_uses == ["Supported use"]
    context.openai.analyze_image.assert_awaited_once_with(b"package photo", "image/png")
    context.cima.search_presentations.assert_awaited_once_with("Example")
    context.cima.get_official_indications.assert_awaited_once_with("000001")
    context.openai.translate_official_uses.assert_awaited_once_with("Official indications")


def test_no_ai_candidate_skips_cima(identification):
    context = identification
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[])

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "not_identified"
    context.cima.search_presentations.assert_not_awaited()
    context.cima.get_official_indications.assert_not_awaited()


def test_multiple_ai_candidates_wait_for_user_selection(identification):
    context = identification
    candidates = [context.candidate, MedicationCandidate(name="Another", strength=None, form=None)]
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=candidates)

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "multiple_matches"
    assert result.candidates == candidates
    assert result.suggested_candidate is None
    assert result.official_uses == []
    context.cima.search_presentations.assert_not_awaited()


@pytest.mark.parametrize("has_presentation", [False, True])
def test_unconfirmed_candidate_has_no_official_uses(identification, has_presentation):
    context = identification
    if has_presentation:
        context.openai.analyze_image.return_value = ImageAnalysisResult(
            candidates=[context.candidate.model_copy(update={"strength": None})]
        )
    else:
        context.cima.search_presentations.return_value = []

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "no_match"
    assert result.suggested_candidate.name == "Example"
    assert result.medication is None
    assert result.official_uses == []
    context.cima.get_official_indications.assert_not_awaited()


def test_multiple_cima_presentations_wait_for_user_selection(identification):
    context = identification
    presentations = [context.medication, context.medication.model_copy(
        update={"registration_number": "000002", "national_code": "000020"}
    )]
    context.cima.search_presentations.return_value = presentations

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "multiple_matches"
    assert result.presentations == presentations
    assert result.medication is None
    assert result.official_uses == []
    context.cima.get_official_indications.assert_not_awaited()


@pytest.mark.parametrize("selection", ["candidate", "national_code"])
def test_user_selection_is_verified_without_image_analysis(identification, selection):
    context = identification
    request = (
        VerifyRequest(candidate=context.candidate)
        if selection == "candidate" else VerifyRequest(national_code="000010")
    )

    result = asyncio.run(context.service.verify(request))

    assert result.status == "verified"
    assert result.medication == context.medication
    context.openai.analyze_image.assert_not_awaited()
    if selection == "national_code":
        context.cima.get_presentation.assert_awaited_once_with("000010")
        context.cima.search_presentations.assert_not_awaited()
    else:
        context.cima.search_presentations.assert_awaited_once_with("Example")


@pytest.mark.parametrize("step", ["image_analysis", "cima_verification"])
@pytest.mark.parametrize("failure", ["connection", "timeout"])
def test_service_failure_returns_connection_error(identification, step, failure):
    context = identification

    if step == "image_analysis":
        request = httpx.Request("POST", "https://example.test")
        error = (
            APIConnectionError(request=request)
            if failure == "connection"
            else APITimeoutError(request=request)
        )
    else:
        error = (
            httpx.ConnectError("Connection failure")
            if failure == "connection"
            else httpx.ReadTimeout("Service timeout")
        )

    processing_calls(context)[step].side_effect = error

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "connection_error"
    assert result.failed_step == step
    assert result.medication is None
    assert result.official_uses == []
    assert (result.retry_token is None) == (step == "image_analysis")


@pytest.mark.parametrize(
    "step, error",
    [
        ("official_uses_retrieval", httpx.ConnectError("Failure")),
        ("official_uses_retrieval", httpx.ReadTimeout("Service timeout")),
        ("uses_translation", ValueError("Incomplete translation")),
        ("uses_translation", APITimeoutError(request=httpx.Request("POST", "https://example.test"))),
    ],
)
def test_official_uses_failure_keeps_verified_medication(identification, step, error):
    context = identification
    processing_calls(context)[step].side_effect = error

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "verified"
    assert result.medication == context.medication
    assert result.official_uses == []
    assert result.retry_token is None
    if step == "official_uses_retrieval":
        context.openai.translate_official_uses.assert_not_awaited()


@pytest.mark.parametrize("step", ["cima_verification", "official_uses_retrieval", "uses_translation"])
def test_global_timeout_retry_skips_completed_steps(identification, monkeypatch, step):
    context = identification
    monkeypatch.setattr("medclue_api.identification.IDENTIFICATION_TIMEOUT_SECONDS", 0.05)
    call = processing_calls(context)[step]

    async def blocked(*args):
        await asyncio.Event().wait()

    call.side_effect = blocked
    first = asyncio.run(context.service.identify(b"package photo"))

    assert first.status == "timeout"
    assert first.failed_step == step
    assert first.medication is None
    assert first.official_uses == []
    assert first.suggested_candidate is not None
    state = context.tokens.read_token(first.retry_token)
    assert state.failed_step == step
    if step == "uses_translation":
        assert state.indications == "Official indications"

    call.side_effect = None
    another_instance = IdentificationService(context.cima, context.openai, RetryTokenManager(TEST_SECRET))
    result = asyncio.run(another_instance.verify(VerifyRequest(retry_token=first.retry_token)))

    assert result.status == "verified"
    assert result.official_uses == ["Supported use"]
    for stage, method in processing_calls(context).items():
        assert method.await_count == (2 if stage == step else 1)


def test_image_analysis_global_timeout_retries_with_same_photo(identification, monkeypatch):
    context = identification
    monkeypatch.setattr("medclue_api.identification.IDENTIFICATION_TIMEOUT_SECONDS", 0.05)

    async def blocked(*args):
        await asyncio.Event().wait()

    context.openai.analyze_image.side_effect = blocked
    first = asyncio.run(context.service.identify(b"same photo"))

    assert first.status == "timeout"
    assert first.failed_step == "image_analysis"
    assert first.retry_token is None
    context.cima.search_presentations.assert_not_awaited()

    context.openai.analyze_image.side_effect = None
    result = asyncio.run(context.service.identify(b"same photo"))

    assert result.status == "verified"
    assert context.openai.analyze_image.await_count == 2
    assert all(call.args == (b"same photo", "image/jpeg") for call in context.openai.analyze_image.await_args_list)


def test_40_second_deadline_is_shared_by_all_steps(identification, monkeypatch):
    assert IDENTIFICATION_TIMEOUT_SECONDS == 40
    context = identification
    monkeypatch.setattr("medclue_api.identification.IDENTIFICATION_TIMEOUT_SECONDS", 0.5)

    async def analyze(*args):
        await asyncio.sleep(0.3)
        return ImageAnalysisResult(candidates=[context.candidate])

    async def search(*args):
        await asyncio.sleep(0.3)
        return [context.medication]

    context.openai.analyze_image.side_effect = analyze
    context.cima.search_presentations.side_effect = search

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "timeout"
    assert result.failed_step == "cima_verification"
    context.cima.get_official_indications.assert_not_awaited()


@pytest.mark.parametrize("step", ["image_analysis", "uses_translation"])
def test_cancellation_propagates_without_continuing(identification, step):
    context = identification

    async def cancel_attempt():
        started = asyncio.Event()

        async def blocked(*args):
            started.set()
            await asyncio.Event().wait()

        processing_calls(context)[step].side_effect = blocked
        task = asyncio.create_task(context.service.identify(b"package photo"))
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_attempt())

    if step == "image_analysis":
        context.cima.search_presentations.assert_not_awaited()
    assert processing_calls(context)[step].await_count == 1
