import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from simulation.llm.base_provider import BaseProvider
from simulation.llm.models import LLMRequest, LLMResponse


# .env dosyasını proje kökünden yükle
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"

loaded = load_dotenv(dotenv_path=ENV_FILE)

print("=" * 60)
print("OpenRouter Debug")
print("=" * 60)
print("Project Root :", ROOT_DIR)
print(".env Path    :", ENV_FILE)
print("Loaded       :", loaded)
print(
    "API Key      :",
    "FOUND" if os.getenv("OPENROUTER_API_KEY") else "NOT FOUND"
)
print("=" * 60)


class OpenRouterProvider(BaseProvider):

    def __init__(self, api_key=None):

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

    def chat(self, request: LLMRequest) -> LLMResponse:

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": request.model or self.default_model,
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

        response = requests.post(
            self.url,
            headers=headers,
            json=payload,
        )

        print("HTTP:", response.status_code)
        print(response.text)

        response.raise_for_status()

        data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self.default_model),
            tokens_used=usage.get("total_tokens", 0),
            finish_reason=choice.get(
                "finish_reason",
                "unknown",
            ),
        )

    def get_model_name(self):

        return self.default_model