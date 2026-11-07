
"""Read backend settings and secrets from the environment."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


CIMA_BASE_URL = "https://cima.aemps.es/cima/rest/"
IDENTIFICATION_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    openai_model: str


def load_settings() -> Settings:
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY must be set and cannot be blank.")

    openai_model = os.getenv("OPENAI_MODEL", "gpt-6.1-terra").strip()
    if not openai_model:
        raise ValueError("OPENAI_MODEL cannot be blank.")

    return Settings(openai_api_key=openai_api_key, openai_model=openai_model)
