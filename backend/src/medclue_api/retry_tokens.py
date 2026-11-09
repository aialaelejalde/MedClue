"""Save identification progress in a secure token for later retries."""

import hashlib
from typing import Literal

from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from medclue_api.config import RETRY_TOKEN_MAX_AGE_SECONDS
from medclue_api.schemas import CimaPresentation, MedicationCandidate


class RetryState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    failed_step: Literal["cima_verification", "official_uses_retrieval", "uses_translation"]
    candidate: MedicationCandidate | None = None
    national_code: str | None = None
    medication: CimaPresentation | None = None
    indications: str | None = None

    @model_validator(mode="after")
    def check_progress(self) -> "RetryState":
        if self.failed_step == "cima_verification":
            if (self.candidate is None) == (self.national_code is None):
                raise ValueError("CIMA verification needs one candidate or national code.")
            if self.national_code is not None and not self.national_code.strip():
                raise ValueError("The national code cannot be blank.")
            if self.medication is not None or self.indications is not None:
                raise ValueError("CIMA verification cannot include confirmed information.")
        else:
            if self.medication is None:
                raise ValueError("Official uses processing needs a confirmed medication.")
            if self.candidate is not None or self.national_code is not None:
                raise ValueError("Use the confirmed medication for official uses processing.")
            if self.failed_step == "official_uses_retrieval" and self.indications is not None:
                raise ValueError("Indications have not been retrieved yet.")
            if self.failed_step == "uses_translation":
                if self.indications is None or not self.indications.strip():
                    raise ValueError("Translation needs the retrieved official indications.")
        return self


class RetryTokenManager:
    def __init__(self, secret: str):
        if not isinstance(secret, str) or len(secret.strip()) < 32:
            raise ValueError("The retry token secret must contain at least 32 characters.")
        self._serializer = URLSafeTimedSerializer(
            secret,
            salt="medclue-identification-retry-v1",
            signer_kwargs={"digest_method": hashlib.sha256},
        )

    def create_token(self, state: RetryState) -> str:
        state = RetryState.model_validate(state.model_dump())
        return self._serializer.dumps(state.model_dump(mode="json"))

    def read_token(self, token: str) -> RetryState:
        if not isinstance(token, str) or not token.strip():
            raise ValueError("A retry token is required.")
        try:
            data = self._serializer.loads(token, max_age=RETRY_TOKEN_MAX_AGE_SECONDS)
            return RetryState.model_validate(data)
        except SignatureExpired as error:
            raise ValueError("The retry token has expired. Start a new identification.") from error
        except (BadData, ValidationError) as error:
            raise ValueError("The retry token is invalid. Start a new identification.") from error
