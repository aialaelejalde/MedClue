"""Test retry token creation and validation."""

import pytest
from itsdangerous.timed import TimestampSigner
from pydantic import ValidationError

from medclue_api.config import RETRY_TOKEN_MAX_AGE_SECONDS
from medclue_api.retry_tokens import RetryState, RetryTokenManager
from medclue_api.schemas import CimaPresentation, MedicationCandidate


TEST_SECRET = "test-retry-secret-with-at-least-32-characters"


@pytest.fixture
def medication():
    return CimaPresentation(
        name="EXAMPLE 500 mg COMPRIMIDOS",
        strength="500 mg",
        form="comprimido",
        registration_number="000001",
        national_code="000010",
    )


@pytest.fixture
def token_manager():
    return RetryTokenManager(TEST_SECRET)


@pytest.mark.parametrize(
    "step",
    ["candidate", "national_code", "official_uses_retrieval", "uses_translation"],
)
def test_retry_state_survives_a_round_trip(token_manager, medication, step):
    if step == "candidate":
        state = RetryState(
            failed_step="cima_verification",
            candidate=MedicationCandidate(name="Example", strength=None, form=None),
        )
    elif step == "national_code":
        state = RetryState(failed_step="cima_verification", national_code="000010")
    else:
        state = RetryState(
            failed_step=step,
            medication=medication,
            indications="Official indications" if step == "uses_translation" else None,
        )

    token = token_manager.create_token(state)

    assert token_manager.read_token(token) == state


def test_another_instance_with_the_same_secret_can_read_the_token(token_manager):
    state = RetryState(failed_step="cima_verification", national_code="000010")
    token = token_manager.create_token(state)
    another_instance = RetryTokenManager(TEST_SECRET)

    assert another_instance.read_token(token) == state


def test_modified_token_is_rejected(token_manager):
    state = RetryState(failed_step="cima_verification", national_code="000010")
    token = token_manager.create_token(state)
    payload, timestamp, signature = token.rsplit(".", 2)
    changed_signature = ("A" if signature[0] != "A" else "B") + signature[1:]

    with pytest.raises(ValueError, match="invalid"):
        token_manager.read_token(f"{payload}.{timestamp}.{changed_signature}")


def test_a_different_secret_cannot_validate_the_token(token_manager):
    state = RetryState(failed_step="cima_verification", national_code="000010")
    token = token_manager.create_token(state)
    another_instance = RetryTokenManager("another-secret-with-at-least-32-characters")

    with pytest.raises(ValueError, match="invalid"):
        another_instance.read_token(token)


def test_expired_token_is_rejected(token_manager, monkeypatch):
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: 1000)
    state = RetryState(failed_step="cima_verification", national_code="000010")
    token = token_manager.create_token(state)
    monkeypatch.setattr(
        TimestampSigner,
        "get_timestamp",
        lambda self: 1000 + RETRY_TOKEN_MAX_AGE_SECONDS + 1,
    )

    with pytest.raises(ValueError, match="expired"):
        token_manager.read_token(token)


@pytest.mark.parametrize("token", ["", "  ", "not-a-signed-token", None])
def test_missing_or_malformed_token_is_rejected(token_manager, token):
    with pytest.raises(ValueError):
        token_manager.read_token(token)


@pytest.mark.parametrize(
    "data",
    [
        {"failed_step": "image_analysis"},
        {"failed_step": "cima_verification"},
        {"failed_step": "cima_verification", "national_code": " "},
        {"failed_step": "official_uses_retrieval"},
        {"failed_step": "uses_translation"},
        {"failed_step": "cima_verification", "national_code": "000010", "photo": "image"},
        {"failed_step": "cima_verification", "national_code": "000010", "notes": "personal"},
        {"failed_step": "cima_verification", "candidate": {"name": "Example", "strength": None, "form": None}, "national_code": "000010"}
    ],
)
def test_invalid_retry_state_is_rejected(data):
    with pytest.raises(ValidationError):
        RetryState.model_validate(data)


@pytest.mark.parametrize("field_name", ["medication", "indications"])
def test_failed_cima_verification_cannot_store_confirmed_data(medication, field_name):
    data = {"failed_step": "cima_verification", "national_code": "000010"}
    data[field_name] = medication if field_name == "medication" else "Official indications"

    with pytest.raises(ValidationError, match="cannot include confirmed information"):
        RetryState.model_validate(data)


@pytest.mark.parametrize("step", ["official_uses_retrieval", "uses_translation"])
@pytest.mark.parametrize("field_name", ["candidate", "national_code"])
def test_retry_after_verification_uses_only_confirmed_medication(medication, step, field_name):
    data = {
        "failed_step": step,
        "medication": medication,
        "indications": "Official indications" if step == "uses_translation" else None,
    }
    data[field_name] = (
        MedicationCandidate(name="Example", strength=None, form=None)
        if field_name == "candidate" else "000010"
    )

    with pytest.raises(ValidationError, match="Use the confirmed medication"):
        RetryState.model_validate(data)


def test_failed_indications_retrieval_cannot_have_indications(medication):
    with pytest.raises(ValidationError, match="Indications have not been retrieved yet"):
        RetryState(
            failed_step="official_uses_retrieval",
            medication=medication,
            indications="Official indications",
        )


@pytest.mark.parametrize("indications", [None, "", "   "])
def test_translation_requires_retrieved_indications(medication, indications):
    with pytest.raises(ValidationError, match="retrieved official indications"):
        RetryState(
            failed_step="uses_translation",
            medication=medication,
            indications=indications,
        )


def test_signed_token_with_invalid_data_is_rejected(token_manager):
    token = token_manager._serializer.dumps({"failed_step": "uses_translation"})

    with pytest.raises(ValueError, match="invalid"):
        token_manager.read_token(token)


def test_modified_state_is_validated_before_signing(token_manager):
    state = RetryState(failed_step="cima_verification", national_code="000010")
    state.national_code = None

    with pytest.raises(ValidationError):
        token_manager.create_token(state)


@pytest.mark.parametrize("secret", ["", "short", " " * 32])
def test_missing_or_short_secret_is_rejected(secret):
    with pytest.raises(ValueError, match="at least 32 characters"):
        RetryTokenManager(secret)
