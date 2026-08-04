import os
import requests

from simulation.llm.base_provider import BaseProvider
from simulation.llm.models import LLMRequest, LLMResponse


class OpenRouterProvider(BaseProvider):

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")

        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY bulunamadı.")

        # Artık ücretsiz olmayan modeli kullanmıyoruz.
        # İleride istediğin modeli buradan değiştirebilirsin.
        self.default_model = "deepseek/deepseek-chat"

        self.url = "https://openrouter.ai/api/v1/chat/completions"

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
                    "content": m.content
                }
                for m in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        response = requests.post(
            self.url,
            headers=headers,
            json=payload
        )

        print("HTTP:", response.status_code)
        print("Sunucu cevabı:")
        print(response.text)

        response.raise_for_status()

        data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self.default_model),
            tokens_used=usage.get("total_tokens", 0),
            finish_reason=choice.get("finish_reason", "unknown"),
        )

    def get_model_name(self):
        return self.default_model