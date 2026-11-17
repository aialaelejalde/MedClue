"""Define and validate API requests, responses, and AI results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


IdentificationStatus = Literal[
    "verified",
    "multiple_matches",
    "not_identified",
    "no_match",
    "connection_error",
    "timeout",
]
ProcessingStep = Literal[
    "image_analysis",
    "cima_verification",
    "official_uses_retrieval",
    "uses_translation",
]


class _Schema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
        str_min_length=1,
    )


class MedicationCandidate(_Schema):
    name: str
    strength: str | None
    form: str | None
    national_code: str | None = Field(default=None, min_length=0)


class ImageAnalysisResult(_Schema):
    candidates: list[MedicationCandidate]


class OfficialUsesResult(_Schema):
    official_uses: list[str]


class CimaPresentation(MedicationCandidate):
    registration_number: str
    national_code: str
    active_ingredients: list[str] = Field(default_factory=list, exclude=True, repr=False)


class VerifyRequest(_Schema):
    """Validate data sent from the Android app to the FastAPI backend to verify a medication or retry a failed step."""

    candidate: MedicationCandidate | None = None
    national_code: str | None = None
    retry_token: str | None = None

    @model_validator(mode="after")
    def check_selection(self) -> "VerifyRequest":
        selections = (
            self.candidate is not None,
            self.national_code is not None,
            self.retry_token is not None,
        )
        if sum(selections) != 1:
            raise ValueError("Send one candidate, national code, or retry token.")
        return self


class IdentificationResponse(_Schema):
    """Validate the medication identification result sent from the FastAPI backend to the Android app."""

    status: IdentificationStatus
    medication: CimaPresentation | None = None
    suggested_candidate: MedicationCandidate | None = None
    candidates: list[MedicationCandidate] = Field(default_factory=list)
    presentations: list[CimaPresentation] = Field(default_factory=list)
    official_uses: list[str] = Field(default_factory=list)
    failed_step: ProcessingStep | None = None
    retry_token: str | None = None

    @model_validator(mode="after")
    def check_result(self) -> "IdentificationResponse":
        if self.status == "verified":
            if self.medication is None:
                raise ValueError("A verified result needs a CIMA presentation.")
            if self.suggested_candidate is not None:
                raise ValueError("A verified result cannot include an unverified AI candidate.")
        elif self.medication is not None or self.official_uses:
            raise ValueError("Unverified results cannot include confirmed data or official uses.")

        if self.status == "multiple_matches":
            self._check_matches()
        elif self.candidates or self.presentations:
            raise ValueError("Only multiple matches can include option lists.")

        if self.status in ("connection_error", "timeout"):
            self._check_failure()
        elif self.status == "verified" and (self.failed_step is not None or self.retry_token is not None):
            if self.failed_step not in ("official_uses_retrieval", "uses_translation"):
                raise ValueError("Only official uses can fail after medication verification.")
            if self.official_uses:
                raise ValueError("Unavailable official uses cannot include labels.")
            self._check_failure()
        elif self.failed_step is not None or self.retry_token is not None:
            raise ValueError("Only a connection error or timeout can include retry details.")

        if self.status == "not_identified" and self.suggested_candidate is not None:
            raise ValueError("An unidentified result cannot include a suggested name.")
        if self.status == "no_match" and self.suggested_candidate is None:
            raise ValueError("A no-match result needs the suggested candidate.")

        return self

    def _check_matches(self) -> None:
        if self.candidates:
            if len(self.candidates) < 2 or self.presentations:
                raise ValueError("Send at least two candidates or presentations.")
            if self.suggested_candidate is not None:
                raise ValueError("Do not select an AI candidate automatically.")
        elif len(self.presentations) < 2:
            raise ValueError("Send at least two candidates or presentations.")

    def _check_failure(self) -> None:
        if self.failed_step is None:
            raise ValueError("State which step failed or timed out.")

        if self.failed_step == "image_analysis":
            if self.suggested_candidate is not None or self.retry_token is not None:
                raise ValueError("Retry image analysis with the same photo.")
        elif self.retry_token is None:
            raise ValueError("A retry token is required to retry this step.")
