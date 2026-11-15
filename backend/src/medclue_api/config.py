"""Read backend settings and secrets from the environment."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


CIMA_BASE_URL = "https://cima.aemps.es/cima/rest/"
IDENTIFICATION_TIMEOUT_SECONDS = 40
RETRY_TOKEN_MAX_AGE_SECONDS = 15 * 60
MIN_RETRY_TOKEN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    openai_model: str
    retry_token_secret: str = field(repr=False)


def load_settings() -> Settings:
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY must be set and cannot be blank.")

    openai_model = os.getenv("OPENAI_MODEL", "gpt-6.1-terra").strip()
    if not openai_model:
        raise ValueError("OPENAI_MODEL cannot be blank.")

    retry_token_secret = os.getenv("RETRY_TOKEN_SECRET", "").strip()
    if len(retry_token_secret) < MIN_RETRY_TOKEN_SECRET_LENGTH:
        raise ValueError(f"RETRY_TOKEN_SECRET must contain at least {MIN_RETRY_TOKEN_SECRET_LENGTH} characters.")

    return Settings(
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        retry_token_secret=retry_token_secret,
    )
