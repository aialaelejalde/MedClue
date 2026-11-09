"""Get official indications and prepare supported English use labels."""

from medclue_api.cima_client import CimaClient
from medclue_api.openai_client import OpenAIClient
from medclue_api.schemas import CimaPresentation, ProcessingStep


class OfficialUsesProcessor:
    """Indications are saved to retry translation without calling CIMA again."""

    def __init__(self, medication: CimaPresentation, cima_client: CimaClient, openai_client: OpenAIClient, indications: str | None = None):
        self._medication = medication
        self._cima_client = cima_client
        self._openai_client = openai_client
        self._indications = indications
        self.current_step: ProcessingStep = ("uses_translation" if indications else "official_uses_retrieval")

    @property
    def indications(self) -> str | None:
        return self._indications

    async def get_uses(self) -> list[str]:
        """Get official indications and translate them into English."""
        if self._indications is None:
            self.current_step = "official_uses_retrieval"
            self._indications = await self._cima_client.get_official_indications(self._medication.registration_number)

        if not self._indications.strip():
            return []

        self.current_step = "uses_translation"
        result = await self._openai_client.translate_official_uses(self._indications)
        return result.official_uses
