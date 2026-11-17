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
    context.cima.get_presentation.assert_not_awaited()
    context.cima.get_official_indications.assert_awaited_once_with("000001")
    context.openai.translate_official_uses.assert_awaited_once_with("Official indications")


@pytest.mark.parametrize("national_code, expected_code", [
    ("998625", "998625"), ("998625.4", "998625"),
    (" 998625.4 ", "998625"), ("000010", "000010"),
])
def test_national_code_identifies_without_a_name_search(identification, national_code, expected_code):
    context = identification
    context.candidate = MedicationCandidate(
        name="Example", strength="500 mg", form="tablet", national_code=national_code,
    )
    context.medication = context.medication.model_copy(update={"national_code": expected_code})
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[context.candidate])
    context.cima.get_presentation.return_value = context.medication

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "verified"
    assert result.medication == context.medication
    assert result.official_uses == ["Supported use"]
    context.cima.get_presentation.assert_awaited_once_with(expected_code)
    context.cima.search_presentations.assert_not_awaited()
    context.openai.analyze_image.assert_awaited_once()
    context.cima.get_official_indications.assert_awaited_once_with("000001")


@pytest.mark.parametrize("national_code", [
    None, "", "invalid", "12345", "1234567", "8470009986254", "998625.44",
    "998625-4", "998625.4 extra", "CN 998625", "９９８６２５",
])
def test_unavailable_or_invalid_national_code_searches_by_name(identification, national_code):
    context = identification
    candidate = MedicationCandidate(name="Example", strength="500 mg", form="tablet", national_code=national_code)
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[candidate])

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "verified"
    assert result.medication == context.medication
    context.cima.get_presentation.assert_not_awaited()
    context.cima.search_presentations.assert_awaited_once_with("Example")
    context.openai.analyze_image.assert_awaited_once()


def test_national_code_without_a_cima_match_falls_back_to_name_search(identification):
    context = identification
    candidate = context.candidate.model_copy(update={"national_code": "998625"})
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[candidate])
    context.cima.get_presentation.return_value = None

    async def search(name):
        context.cima.get_presentation.assert_awaited_once_with("998625")
        return [context.medication]

    context.cima.search_presentations.side_effect = search

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "verified"
    context.cima.search_presentations.assert_awaited_once_with("Example")
    context.openai.analyze_image.assert_awaited_once()


@pytest.mark.parametrize("changes", [
    {"name": "Another"},
    {"name": "Example Forte"},
    {"strength": "250 mg"},
    {"form": "capsule"},
    {"name": "Example 250 mg tablets", "strength": None},
    {"name": "Example 500 mg capsules", "form": None},
    {"name": "Example 500 mg capsules"},
    {"name": "Example capsules", "strength": None, "form": None},
])
def test_conflicting_national_code_keeps_only_original_photo_data(identification, changes):
    context = identification
    candidate = context.candidate.model_copy(update={"national_code": "000010", **changes})
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[candidate])

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "no_match"
    assert result.suggested_candidate == candidate
    assert result.medication is None
    assert result.presentations == []
    assert result.official_uses == []
    context.cima.get_presentation.assert_awaited_once_with("000010")
    context.cima.search_presentations.assert_not_awaited()
    context.cima.get_official_indications.assert_not_awaited()
    context.openai.translate_official_uses.assert_not_awaited()


@pytest.mark.parametrize("candidate_changes, official_changes", [
    ({"strength": "0,5 g", "form": "TABLETS"}, {}),
    ({"name": " Éxample ", "strength": None, "form": None}, {}),
    ({}, {"strength": None, "form": None}),
    ({"name": "Example-Plus"}, {"name": "EXAMPLE PLUS 500 mg COMPRIMIDOS"}),
    ({"name": "Example 0.5 g tablets", "strength": None, "form": None}, {}),
    ({"strength": None, "form": None}, {"name": "Example", "strength": None, "form": None}),
    ({"strength": "5%", "form": "cream"}, {"name": "EXAMPLE 5% CREMA", "strength": "5%", "form": "crema"}),
    ({"strength": None, "form": None}, {"name": "EXAMPLE COMPRIMIDOS", "strength": None, "form": None}),
    ({"form": "film-coated tablet"}, {"form": "COMPRIMIDO RECUBIERTO CON PELÍCULA"}),
])
def test_code_matching_accepts_equivalent_or_missing_details(identification, candidate_changes, official_changes):
    context = identification
    candidate = context.candidate.model_copy(update={"national_code": "000010", **candidate_changes})
    official = context.medication.model_copy(update=official_changes)
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[candidate])
    context.cima.get_presentation.return_value = official

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "verified"
    assert result.medication == official
    context.cima.search_presentations.assert_not_awaited()


def test_uncertain_code_match_stays_unconfirmed_without_searching_again(identification):
    context = identification
    candidate = context.candidate.model_copy(update={"national_code": "000010", "strength": "unclear"})
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[candidate])

    result = asyncio.run(context.service.identify(b"package photo"))

    assert result.status == "no_match"
    assert result.suggested_candidate == candidate
    context.cima.search_presentations.assert_not_awaited()
    context.cima.get_official_indications.assert_not_awaited()


@pytest.mark.parametrize("failure", ["connection", "timeout"])
def test_code_lookup_failure_retries_with_code_and_original_candidate(identification, monkeypatch, failure):
    context = identification
    candidate = context.candidate.model_copy(update={"national_code": "000010.4"})
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[candidate])

    async def fail(*args):
        if failure == "connection":
            raise httpx.ConnectError("Offline")
        await asyncio.Event().wait()

    monkeypatch.setattr("medclue_api.identification.IDENTIFICATION_TIMEOUT_SECONDS", 0.05)
    context.cima.get_presentation.side_effect = fail
    first = asyncio.run(context.service.identify(b"package photo"))

    assert first.status == ("connection_error" if failure == "connection" else "timeout")
    assert first.failed_step == "cima_verification"
    assert first.suggested_candidate == candidate
    assert context.tokens.read_token(first.retry_token).candidate == candidate
    context.cima.search_presentations.assert_not_awaited()

    context.cima.get_presentation.side_effect = None
    # A contradictory retry result must still be checked against the photo data.
    context.cima.get_presentation.return_value = context.medication.model_copy(update={"name": "Another"})
    result = asyncio.run(context.service.process_selection_or_retry(VerifyRequest(retry_token=first.retry_token)))

    assert result.status == "no_match"
    assert result.suggested_candidate == candidate
    assert context.cima.get_presentation.await_count == 2
    assert all(call.args == ("000010",) for call in context.cima.get_presentation.await_args_list)
    context.openai.analyze_image.assert_awaited_once()
    context.cima.search_presentations.assert_not_awaited()
    context.cima.get_official_indications.assert_not_awaited()


def test_selected_ai_candidate_keeps_its_code_without_reanalyzing(identification):
    context = identification
    candidate = context.candidate.model_copy(update={"national_code": "000010"})
    context.openai.analyze_image.return_value = ImageAnalysisResult(candidates=[
        candidate, MedicationCandidate(name="Another", strength=None, form=None),
    ])

    first = asyncio.run(context.service.identify(b"photo"))
    context.cima.get_presentation.assert_not_awaited()
    result = asyncio.run(context.service.process_selection_or_retry(VerifyRequest(candidate=first.candidates[0])))

    assert result.status == "verified"
    context.cima.get_presentation.assert_awaited_once_with("000010")
    context.cima.search_presentations.assert_not_awaited()
    context.openai.analyze_image.assert_awaited_once()


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

    result = asyncio.run(context.service.process_selection_or_retry(request))

    assert result.status == "verified"
    assert result.medication == context.medication
    context.openai.analyze_image.assert_not_awaited()
    if selection == "national_code":
        context.cima.get_presentation.assert_awaited_once_with("000010")
        context.cima.search_presentations.assert_not_awaited()
    else:
        context.cima.search_presentations.assert_awaited_once_with("Example")


def test_missing_selected_presentation_raises_lookup_error_without_processing_uses(identification):
    context = identification
    context.cima.get_presentation.return_value = None
    request = VerifyRequest(national_code="000010")

    with pytest.raises(LookupError, match="selected CIMA presentation was not found"):
        asyncio.run(context.service.process_selection_or_retry(request))

    context.cima.get_presentation.assert_awaited_once_with("000010")
    context.cima.get_official_indications.assert_not_awaited()
    context.openai.translate_official_uses.assert_not_awaited()


def test_invalid_retry_token_is_rejected_without_external_requests(identification):
    context = identification
    request = VerifyRequest(retry_token="invalid-token")

    with pytest.raises(ValueError, match="retry token is invalid"):
        asyncio.run(context.service.process_selection_or_retry(request))

    context.openai.analyze_image.assert_not_awaited()
    context.cima.search_presentations.assert_not_awaited()
    context.cima.get_presentation.assert_not_awaited()
    context.cima.get_official_indications.assert_not_awaited()
    context.openai.translate_official_uses.assert_not_awaited()


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
    assert result.failed_step == step
    state = context.tokens.read_token(result.retry_token)
    assert state.failed_step == step
    assert state.medication == context.medication
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

    assert first.status == ("timeout" if step == "cima_verification" else "verified")
    assert first.failed_step == step
    assert first.medication == (None if step == "cima_verification" else context.medication)
    assert first.official_uses == []
    assert (first.suggested_candidate is not None) == (step == "cima_verification")
    state = context.tokens.read_token(first.retry_token)
    assert state.failed_step == step
    if step == "uses_translation":
        assert state.indications == "Official indications"

    call.side_effect = None
    another_instance = IdentificationService(context.cima, context.openai, RetryTokenManager(TEST_SECRET))
    result = asyncio.run(another_instance.process_selection_or_retry(VerifyRequest(retry_token=first.retry_token)))

    assert result.status == "verified"
    assert result.official_uses == ["Supported use"]
    for stage, method in processing_calls(context).items():
        assert method.await_count == (2 if stage == step else 1)


@pytest.mark.parametrize("step", ["official_uses_retrieval", "uses_translation"])
def test_official_uses_error_can_retry_without_reidentifying(identification, step):
    context = identification
    call = processing_calls(context)[step]
    call.side_effect = ValueError("Invalid provider response")
    first = asyncio.run(context.service.identify(b"package photo"))
    assert first.status == "verified"
    assert first.failed_step == step

    call.side_effect = None
    result = asyncio.run(context.service.process_selection_or_retry(VerifyRequest(retry_token=first.retry_token)))

    assert result.status == "verified"
    assert result.medication == context.medication
    assert result.official_uses == ["Supported use"]
    assert result.failed_step is None
    assert result.retry_token is None
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
