"""Set up FastAPI and connect the backend modules."""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from medclue_api.cima_client import CimaClient
from medclue_api.config import load_settings
from medclue_api.identification import IdentificationService
from medclue_api.openai_client import OpenAIClient
from medclue_api.retry_tokens import RetryTokenManager
from medclue_api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = load_settings()
    token_manager = RetryTokenManager(settings.retry_token_secret)

    async with AsyncExitStack() as resources:
        cima_client = CimaClient()
        resources.push_async_callback(cima_client.close)
        openai_client = OpenAIClient(settings)
        resources.push_async_callback(openai_client.close)

        app.state.identification_service = IdentificationService(
            cima_client, openai_client, token_manager
        )
        try:
            yield
        finally:
            app.state.identification_service = None


app = FastAPI(title="MedClue", version="0.1.0", lifespan=lifespan)
app.include_router(router)
