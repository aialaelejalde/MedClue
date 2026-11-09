"""Test official use processing without calling external services."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from medclue_api.official_uses import OfficialUsesProcessor
from medclue_api.schemas import CimaPresentation, OfficialUsesResult


@pytest.fixture
def official_uses():
    medication = CimaPresentation(
        name="EXAMPLE 500 mg COMPRIMIDOS",
        strength="500 mg",
        form="comprimido",
        registration_number="000001",
        national_code="000010",
    )
    cima_client = SimpleNamespace(
        get_official_indications=AsyncMock(return_value="Official indications")
    )
    openai_client = SimpleNamespace(
        translate_official_uses=AsyncMock(
            return_value=OfficialUsesResult(official_uses=["Supported use"])
        )
    )
    processor = OfficialUsesProcessor(medication, cima_client, openai_client)
    return processor, cima_client, openai_client


def test_official_indications_are_retrieved_and_translated(official_uses):
    processor, cima_client, openai_client = official_uses

    uses = asyncio.run(processor.get_uses())

    assert uses == ["Supported use"]
    cima_client.get_official_indications.assert_awaited_once_with("000001")
    openai_client.translate_official_uses.assert_awaited_once_with("Official indications")


@pytest.mark.parametrize("indications", ["", " \t\n "])
def test_empty_indications_skip_translation(official_uses, indications):
    processor, cima_client, openai_client = official_uses
    cima_client.get_official_indications.return_value = indications

    assert asyncio.run(processor.get_uses()) == []
    openai_client.translate_official_uses.assert_not_awaited()


def test_empty_translation_returns_no_uses(official_uses):
    processor, _, openai_client = official_uses
    openai_client.translate_official_uses.return_value = OfficialUsesResult(official_uses=[])

    assert asyncio.run(processor.get_uses()) == []


def test_retrieval_failure_can_be_retried(official_uses):
    processor, cima_client, openai_client = official_uses
    cima_client.get_official_indications.side_effect = [
        httpx.ConnectError("Simulated connection failure"),
        "Official indications",
    ]

    with pytest.raises(httpx.ConnectError):
        asyncio.run(processor.get_uses())

    assert processor.current_step == "official_uses_retrieval"
    openai_client.translate_official_uses.assert_not_awaited()
    assert asyncio.run(processor.get_uses()) == ["Supported use"]
    assert cima_client.get_official_indications.await_count == 2


@pytest.mark.parametrize(
    "error",
    [ValueError("Incomplete translation"), httpx.ReadTimeout("Simulated timeout")],
)
def test_translation_retry_reuses_retrieved_indications(official_uses, error):
    processor, cima_client, openai_client = official_uses
    openai_client.translate_official_uses.side_effect = [
        error,
        OfficialUsesResult(official_uses=["Supported use"]),
    ]

    with pytest.raises(type(error)):
        asyncio.run(processor.get_uses())

    assert processor.current_step == "uses_translation"
    assert asyncio.run(processor.get_uses()) == ["Supported use"]
    cima_client.get_official_indications.assert_awaited_once()
    assert openai_client.translate_official_uses.await_count == 2


def test_cancellation_stops_before_translation(official_uses):
    processor, cima_client, openai_client = official_uses
    cima_client.get_official_indications.side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(processor.get_uses())

    assert processor.current_step == "official_uses_retrieval"
    openai_client.translate_official_uses.assert_not_awaited()
