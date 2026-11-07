"""Call OpenAI to read package photos and process official indications."""

import base64

from openai import AsyncOpenAI

from medclue_api.config import IDENTIFICATION_TIMEOUT_SECONDS, Settings
from medclue_api.prompts import IMAGE_ANALYSIS_PROMPT, OFFICIAL_USES_PROMPT
from medclue_api.schemas import ImageAnalysisResult, OfficialUsesResult


class OpenAIClient:
    def __init__(self, settings: Settings):
        self._model = settings.openai_model
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=IDENTIFICATION_TIMEOUT_SECONDS,
            max_retries=0,
        )

    async def analyze_image(self, photo: bytes, media_type: str = "image/jpeg") -> ImageAnalysisResult:
        if not isinstance(photo, bytes) or not photo:
            raise ValueError("The photo must contain image bytes.")
        if media_type not in ("image/jpeg", "image/png", "image/webp"):
            raise ValueError("The photo must use JPEG, PNG, or WebP format.")

        encoded_photo = base64.b64encode(photo).decode("ascii")
        response = await self._client.responses.parse(
            model=self._model,
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
        if response.status != "completed" or response.output_parsed is None:
            raise ValueError("OpenAI did not return a complete image analysis result.")

        return response.output_parsed

    async def translate_official_uses(self, indications: str) -> OfficialUsesResult:
        if not isinstance(indications, str):
            raise ValueError("Official indications must be text.")
        if not indications.strip():
            return OfficialUsesResult(official_uses=[])

        response = await self._client.responses.parse(
            model=self._model,
            instructions=OFFICIAL_USES_PROMPT,
            input=[{"role": "user", "content": indications}],
            text_format=OfficialUsesResult,
            store=False,
        )
        if response.status != "completed" or response.output_parsed is None:
            raise ValueError("OpenAI did not return a complete official uses result.")

        return response.output_parsed

    async def close(self) -> None:
        await self._client.close()
