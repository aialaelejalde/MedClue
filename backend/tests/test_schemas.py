"""Test validation of backend API requests, identification responses, and AI results."""

import json

import pytest
from pydantic import ValidationError

from medclue_api.schemas import (
    CimaPresentation,
    IdentificationResponse,
    ImageAnalysisResult,
    MedicationCandidate,
    OfficialUsesResult,
    VerifyRequest,
)


@pytest.fixture
def candidate():
    return {"name": "Example medicine", "strength": None, "form": None}


@pytest.fixture
def presentation(candidate):
    return {
        **candidate,
        "registration_number": "000001",
        "national_code": "000002",
    }


@pytest.fixture
def response_payloads(candidate, presentation):
    return {
        "verified": {"status": "verified", "medication": presentation},
        "multiple_matches": {
            "status": "multiple_matches",
            "candidates": [candidate, {**candidate, "name": "Another medicine"}],
        },
        "not_identified": {"status": "not_identified"},
        "no_match": {"status": "no_match", "suggested_candidate": candidate},
        "connection_error": {
            "status": "connection_error",
            "failed_step": "cima_verification",
            "suggested_candidate": candidate,
            "retry_token": "example-backend-token",
        },
        "timeout": {
            "status": "timeout",
            "failed_step": "uses_translation",
            "suggested_candidate": candidate,
            "retry_token": "example-backend-token",
        },
    }


def test_candidate_accepts_null_strength_and_form(candidate):
    result = MedicationCandidate.model_validate_json(json.dumps(candidate))

    assert result.strength is None
    assert result.form is None


def test_candidate_strips_outer_spaces_from_name(candidate):
    candidate["name"] = "  Example medicine  "

    result = MedicationCandidate.model_validate_json(json.dumps(candidate))

    assert result.name == "Example medicine"


@pytest.mark.parametrize("field_name", ["name", "strength", "form"])
def test_candidate_requires_all_fields_even_when_values_can_be_null(candidate, field_name):
    del candidate[field_name]

    with pytest.raises(ValidationError):
        MedicationCandidate.model_validate_json(json.dumps(candidate))


@pytest.mark.parametrize(
    "field_name, value",
    [
        ("name", " "), ("name", None), ("name", 123),
        ("strength", " "), ("strength", 500),
        ("form", " "), ("form", False),
    ],
)
def test_candidate_rejects_blank_text_and_wrong_types(candidate, field_name, value):
    candidate[field_name] = value

    with pytest.raises(ValidationError):
        MedicationCandidate.model_validate_json(json.dumps(candidate))


@pytest.mark.parametrize("candidate_count", [0, 1, 2])
def test_image_analysis_accepts_empty_single_and_multiple_results(candidate_count):
    payload = {
        "candidates": [
            {"name": f"Example {number}", "strength": "500 mg", "form": "tablet"}
            for number in range(candidate_count)
        ]
    }

    result = ImageAnalysisResult.model_validate_json(json.dumps(payload))

    assert len(result.candidates) == candidate_count


@pytest.mark.parametrize("labels", [[], ["Example label", "Another label"]])
def test_official_uses_accepts_labels_or_an_empty_list(labels):
    result = OfficialUsesResult.model_validate_json(
        json.dumps({"official_uses": labels})
    )

    assert result.official_uses == labels


@pytest.mark.parametrize("labels", [[" "], [123], [None], "Example label", None])
def test_official_uses_rejects_invalid_labels_and_wrong_list_types(labels):
    with pytest.raises(ValidationError):
        OfficialUsesResult.model_validate_json(json.dumps({"official_uses": labels}))


def test_presentation_excludes_active_ingredients_from_serialization(presentation):
    result = CimaPresentation.model_validate({
        **presentation,
        "active_ingredients": ["Example ingredient"],
    })

    assert "active_ingredients" not in result.model_dump()


@pytest.mark.parametrize("field_name", ["registration_number", "national_code"])
@pytest.mark.parametrize("value", [" ", 123, None])
def test_presentation_rejects_invalid_identifiers(presentation, field_name, value):
    presentation[field_name] = value

    with pytest.raises(ValidationError):
        CimaPresentation.model_validate_json(json.dumps(presentation))


@pytest.mark.parametrize("selection", ["candidate", "national_code", "retry_token"])
def test_verification_accepts_each_single_selection(candidate, selection):
    choices = {
        "candidate": candidate,
        "national_code": "000002",
        "retry_token": "example-backend-token",
    }
    payload = {selection: choices[selection]}

    result = VerifyRequest.model_validate_json(json.dumps(payload))

    assert result.model_dump()[selection] == payload[selection]


@pytest.mark.parametrize(
    "selections",
    [
        [], ["candidate", "national_code"], ["candidate", "retry_token"],
        ["national_code", "retry_token"],
        ["candidate", "national_code", "retry_token"],
    ],
)
def test_verification_rejects_missing_or_multiple_selections(candidate, selections):
    choices = {
        "candidate": candidate,
        "national_code": "000002",
        "retry_token": "example-backend-token",
    }
    payload = {selection: choices[selection] for selection in selections}

    with pytest.raises(ValidationError, match="Send one"):
        VerifyRequest.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "status",
    [
        "verified", "multiple_matches", "not_identified", "no_match",
        "connection_error", "timeout",
    ],
)
def test_each_approved_status_accepts_its_data(response_payloads, status):
    result = IdentificationResponse.model_validate_json(
        json.dumps(response_payloads[status])
    )

    assert result.status == status


def test_verified_result_accepts_official_uses(presentation):
    labels = ["Example official label"]
    result = IdentificationResponse.model_validate_json(
        json.dumps({
            "status": "verified", "medication": presentation,
            "official_uses": labels,
        })
    )

    assert result.official_uses == labels


@pytest.mark.parametrize(
    "status",
    ["multiple_matches", "not_identified", "no_match", "connection_error", "timeout"],
)
@pytest.mark.parametrize("field_name", ["medication", "official_uses"])
def test_unverified_results_reject_confirmed_data(response_payloads, presentation, status, field_name):
    payload = response_payloads[status]
    payload[field_name] = (
        presentation if field_name == "medication" else ["Example label"]
    )

    with pytest.raises(ValidationError, match="Unverified results"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


def test_multiple_cima_presentations_are_valid_options(candidate, presentation):
    payload = {
        "status": "multiple_matches",
        "suggested_candidate": candidate,
        "presentations": [presentation, {**presentation, "national_code": "000003"}],
    }

    result = IdentificationResponse.model_validate_json(json.dumps(payload))

    assert len(result.presentations) == 2


@pytest.mark.parametrize(
    "option_field, option_count",
    [
        ("candidates", 0),
        ("candidates", 1),
        ("presentations", 0),
        ("presentations", 1),
    ],
)
def test_multiple_matches_requires_at_least_two_options(candidate, presentation, option_field, option_count):
    option = candidate if option_field == "candidates" else presentation
    payload = {"status": "multiple_matches", option_field: [option] * option_count}

    with pytest.raises(ValidationError, match="at least two"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


def test_ai_candidates_and_cima_presentations_cannot_be_mixed(response_payloads, presentation):
    payload = response_payloads["multiple_matches"]
    payload["presentations"] = [presentation, {**presentation, "national_code": "000003"}]

    with pytest.raises(ValidationError, match="at least two candidates or presentations"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


def test_multiple_ai_candidates_cannot_include_an_automatic_selection(response_payloads, candidate):
    payload = response_payloads["multiple_matches"]
    payload["suggested_candidate"] = candidate

    with pytest.raises(ValidationError, match="automatically"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("status", ["connection_error", "timeout"])
@pytest.mark.parametrize(
    "step",
    [
        "image_analysis", "cima_verification", "official_uses_retrieval",
        "uses_translation",
    ],
)
def test_errors_accept_the_failed_step_and_its_retry_data(candidate, status, step):
    payload = {"status": status, "failed_step": step}
    if step != "image_analysis":
        payload["suggested_candidate"] = candidate
        payload["retry_token"] = "example-backend-token"

    result = IdentificationResponse.model_validate_json(json.dumps(payload))

    assert result.failed_step == step
    assert result.retry_token == payload.get("retry_token")
    assert (
        result.suggested_candidate.model_dump()
        if result.suggested_candidate is not None else None
    ) == payload.get("suggested_candidate")


@pytest.mark.parametrize("status", ["connection_error", "timeout"])
def test_errors_require_the_failed_step(status):
    with pytest.raises(ValidationError, match="which step"):
        IdentificationResponse.model_validate_json(json.dumps({"status": status}))


@pytest.mark.parametrize("status", ["connection_error", "timeout"])
@pytest.mark.parametrize("step", ["cima_verification", "official_uses_retrieval", "uses_translation"])
def test_retries_after_image_analysis_require_a_backend_token(candidate, status, step):
    payload = {"status": status, "failed_step": step, "suggested_candidate": candidate}

    with pytest.raises(ValidationError, match="retry token"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("field_name", ["suggested_candidate", "retry_token"])
def test_failed_image_analysis_does_not_include_later_results(candidate, field_name):
    payload = {"status": "connection_error", "failed_step": "image_analysis"}
    payload[field_name] = candidate if field_name == "suggested_candidate" else "token"

    with pytest.raises(ValidationError, match="same photo"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("status", ["multiple_matches", "not_identified", "no_match"])
@pytest.mark.parametrize("field_name", ["failed_step", "retry_token"])
def test_completed_results_cannot_include_retry_details(response_payloads, status, field_name):
    payload = response_payloads[status]
    payload[field_name] = "image_analysis" if field_name == "failed_step" else "token"

    with pytest.raises(ValidationError, match="Only a connection error or timeout"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("step", ["official_uses_retrieval", "uses_translation"])
def test_verified_medication_can_include_retry_for_unavailable_uses(presentation, step):
    result = IdentificationResponse(
        status="verified", medication=presentation, failed_step=step, retry_token="signed-token",
    )
    assert result.failed_step == step
    assert result.official_uses == []


@pytest.mark.parametrize("fields", [
    {"retry_token": "token"},
    {"failed_step": "image_analysis", "retry_token": "token"},
    {"failed_step": "cima_verification", "retry_token": "token"},
    {"failed_step": "uses_translation"},
    {"failed_step": "uses_translation", "retry_token": "token", "official_uses": ["Use"]},
])
def test_verified_retry_rejects_inconsistent_partial_results(presentation, fields):
    with pytest.raises(ValidationError):
        IdentificationResponse(status="verified", medication=presentation, **fields)


@pytest.mark.parametrize(
    "schema, payload",
    [
        (ImageAnalysisResult, {"candidates": []}),
        (OfficialUsesResult, {"official_uses": []}),
        (VerifyRequest, {"national_code": "000002"}),
        (IdentificationResponse, {"status": "not_identified"}),
    ],
)
def test_unknown_fields_are_rejected(schema, payload):
    with pytest.raises(ValidationError, match="Extra inputs"):
        schema.model_validate_json(json.dumps({**payload, "unexpected_field": "value"}))


def test_invalid_status_is_rejected():
    with pytest.raises(ValidationError):
        IdentificationResponse.model_validate_json('{"status": "unknown"}')


def test_verified_result_requires_a_presentation():
    with pytest.raises(ValidationError, match="needs a CIMA presentation"):
        IdentificationResponse.model_validate_json('{"status": "verified"}')


def test_no_match_requires_the_suggested_candidate():
    with pytest.raises(ValidationError, match="needs the suggested candidate"):
        IdentificationResponse.model_validate_json('{"status": "no_match"}')


def test_unidentified_result_cannot_include_a_suggested_candidate(candidate):
    payload = {"status": "not_identified", "suggested_candidate": candidate}

    with pytest.raises(ValidationError, match="cannot include a suggested name"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


def test_verified_result_cannot_include_an_unverified_candidate(response_payloads, candidate):
    payload = response_payloads["verified"]
    payload["suggested_candidate"] = candidate

    with pytest.raises(ValidationError, match="unverified AI candidate"):
        IdentificationResponse.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("status", ["verified", "not_identified", "no_match", "connection_error", "timeout"])
@pytest.mark.parametrize("option_field", ["candidates", "presentations"])
def test_selection_lists_are_only_allowed_for_multiple_matches(response_payloads, candidate, presentation, status, option_field):
    payload = response_payloads[status]
    payload[option_field] = [candidate if option_field == "candidates" else presentation]

    with pytest.raises(ValidationError, match="Only multiple matches"):
        IdentificationResponse.model_validate_json(json.dumps(payload))
