import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from simulation.llm.base_provider import (
    BaseProvider,
    ProviderError,
)
from simulation.llm.models import LLMRequest, LLMResponse


ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = (10, 120)


class OpenRouterProvider(BaseProvider):

    def __init__(self, api_key=None, timeout=REQUEST_TIMEOUT):

        self.api_key = api_key or os.getenv(
            "OPENROUTER_API_KEY"
        )

        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY bulunamadı."
            )

        self.default_model = "deepseek/deepseek-chat"

        self.url = (
            "https://openrouter.ai/api/v1/chat/completions"
        )

        self.timeout = timeout

    def chat(self, request: LLMRequest) -> LLMResponse:

        model = request.model or self.default_model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                }
                for m in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        try:

            response = requests.post(
                self.url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:

            raise ProviderError(
                "OpenRouter request failed: "
                f"{exc.__class__.__name__}"
            ) from exc

        logger.debug(
            "OpenRouter HTTP %s model=%s",
            response.status_code,
            model,
        )

        if response.status_code >= 400:

            raise ProviderError(
                "OpenRouter returned HTTP "
                f"{response.status_code}."
            )

        try:

            data = response.json()

            choice = data["choices"][0]

            content = choice["message"]["content"]

            usage = data.get("usage", {})

        except (ValueError, KeyError, IndexError, TypeError) as exc:

            raise ProviderError(
                "OpenRouter returned an "
                "unparseable response."
            ) from exc

        return LLMResponse(
            content=content,
            model=data.get("model", model),
            tokens_used=usage.get("total_tokens", 0),
            finish_reason=choice.get(
                "finish_reason",
                "unknown",
            ),
        )

    def get_model_name(self):

        return self.default_model
