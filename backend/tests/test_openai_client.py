"""Test image analysis and official use translation using simulated OpenAI responses."""

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from medclue_api.config import Settings
from medclue_api.openai_client import OpenAIClient
from medclue_api.prompts import IMAGE_ANALYSIS_PROMPT, OFFICIAL_USES_PROMPT
from medclue_api.schemas import ImageAnalysisResult, MedicationCandidate, OfficialUsesResult


@pytest.fixture
def openai_client(monkeypatch):
    parse = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            output_parsed=ImageAnalysisResult(candidates=[]),
        )
    )
    sdk_client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    monkeypatch.setattr(
        "medclue_api.openai_client.AsyncOpenAI",
        Mock(return_value=sdk_client),
    )
    settings = Settings(openai_api_key="test-key", openai_model="test-model")
    return OpenAIClient(settings), parse


@pytest.mark.parametrize(
    "photo, media_type",
    [(b"", "image/jpeg"), ("photo", "image/jpeg"), (b"photo", "image/gif")],
)
def test_invalid_images_are_rejected_without_calling_openai(openai_client, photo, media_type):
    client, parse = openai_client

    with pytest.raises(ValueError):
        asyncio.run(client.analyze_image(photo, media_type))

    parse.assert_not_awaited()


@pytest.mark.parametrize("media_type", ["image/jpeg", "image/png", "image/webp"])
def test_image_is_sent_with_the_expected_request(openai_client, media_type):
    client, parse = openai_client
    photo = b"package photo"
    encoded_photo = base64.b64encode(photo).decode("ascii")

    asyncio.run(client.analyze_image(photo, media_type))

    parse.assert_awaited_once_with(
        model="test-model",
        instructions=IMAGE_ANALYSIS_PROMPT,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:{media_type};base64,{encoded_photo}",
                        "detail": "high",
                    }
                ],
            }
        ],
        text_format=ImageAnalysisResult,
        store=False,
    )


def test_image_analysis_returns_the_received_candidates(openai_client):
    client, parse = openai_client
    candidates = [
        MedicationCandidate(name="Example", strength="500 mg", form="tablet"),
        MedicationCandidate(name="Another medicine", strength=None, form=None),
    ]
    parse.return_value.output_parsed = ImageAnalysisResult(candidates=candidates)

    result = asyncio.run(client.analyze_image(b"package photo"))

    assert result.candidates == candidates
    parse.assert_awaited_once()


@pytest.mark.parametrize(
    "status, has_result",
    [("incomplete", True), ("incomplete", False), ("completed", False)],
)
def test_incomplete_openai_responses_are_rejected(openai_client, status, has_result):
    client, parse = openai_client
    parse.return_value = SimpleNamespace(
        status=status,
        output_parsed=ImageAnalysisResult(candidates=[]) if has_result else None,
    )

    with pytest.raises(ValueError, match="complete image analysis result"):
        asyncio.run(client.analyze_image(b"package photo"))

    parse.return_value.output_parsed = OfficialUsesResult(official_uses=[]) if has_result else None

    with pytest.raises(ValueError, match="complete official uses result"):
        asyncio.run(client.translate_official_uses("Official indication"))


@pytest.mark.parametrize("indications", ["", " \t\n "])
def test_empty_indications_return_no_uses_without_calling_openai(openai_client, indications):
    client, parse = openai_client

    result = asyncio.run(client.translate_official_uses(indications))

    assert result.official_uses == []
    parse.assert_not_awaited()


def test_translation_sends_the_indications_and_returns_official_uses(openai_client):
    client, parse = openai_client
    indications = "Alivio del dolor leve en adultos."
    parse.return_value.output_parsed = OfficialUsesResult(
        official_uses=["Relief of mild pain in adults"]
    )

    result = asyncio.run(client.translate_official_uses(indications))

    assert result.official_uses == ["Relief of mild pain in adults"]
    parse.assert_awaited_once_with(
        model="test-model",
        instructions=OFFICIAL_USES_PROMPT,
        input=[{"role": "user", "content": indications}],
        text_format=OfficialUsesResult,
        store=False,
    )
