import logging

import pytest
import requests

from simulation.llm.base_provider import ProviderError
from simulation.llm.models import LLMRequest, Message
from simulation.llm.openrouter_provider import (
    REQUEST_TIMEOUT,
    OpenRouterProvider,
)


class FakeResponse:

    def __init__(
        self,
        status_code,
        json_payload=None,
        json_error=None
    ):

        self.status_code = status_code

        self._json_payload = json_payload

        self._json_error = json_error

    def json(self):

        if self._json_error is not None:

            raise self._json_error

        return self._json_payload


def make_request():
    return LLMRequest(
        messages=[
            Message(role="user", content="test")
        ]
    )


def make_provider():
    return OpenRouterProvider(
        api_key="sk-test-provider-key"
    )


def test_provider_requires_api_key(monkeypatch):

    monkeypatch.delenv(
        "OPENROUTER_API_KEY",
        raising=False,
    )

    with pytest.raises(ValueError):

        OpenRouterProvider(api_key=None)


def test_provider_uses_configured_timeout(monkeypatch):

    captured = {}

    def fake_post(url, headers, json, timeout):

        captured["timeout"] = timeout

        return FakeResponse(
            200,
            json_payload={
                "choices": [
                    {
                        "message": {
                            "content": "ok"
                        }
                    }
                ],
                "model": "deepseek/deepseek-chat",
                "usage": {
                    "total_tokens": 3
                },
            },
        )

    monkeypatch.setattr(
        "simulation.llm.openrouter_provider.requests.post",
        fake_post,
    )

    provider = make_provider()

    result = provider.chat(make_request())

    assert result.content == "ok"

    assert captured["timeout"] == REQUEST_TIMEOUT


def test_provider_wraps_timeout_as_provider_error(monkeypatch):

    def fake_post(url, headers, json, timeout):

        raise requests.exceptions.Timeout()

    monkeypatch.setattr(
        "simulation.llm.openrouter_provider.requests.post",
        fake_post,
    )

    with pytest.raises(ProviderError):

        make_provider().chat(make_request())


def test_provider_wraps_connection_error_as_provider_error(
    monkeypatch
):

    def fake_post(url, headers, json, timeout):

        raise requests.exceptions.ConnectionError()

    monkeypatch.setattr(
        "simulation.llm.openrouter_provider.requests.post",
        fake_post,
    )

    with pytest.raises(ProviderError):

        make_provider().chat(make_request())


def test_provider_wraps_http_error_as_provider_error(monkeypatch):

    def fake_post(url, headers, json, timeout):

        return FakeResponse(500)

    monkeypatch.setattr(
        "simulation.llm.openrouter_provider.requests.post",
        fake_post,
    )

    with pytest.raises(ProviderError):

        make_provider().chat(make_request())


def test_provider_wraps_malformed_json_as_provider_error(
    monkeypatch
):

    def fake_post(url, headers, json, timeout):

        return FakeResponse(
            200,
            json_error=ValueError(
                "No JSON object could be decoded"
            ),
        )

    monkeypatch.setattr(
        "simulation.llm.openrouter_provider.requests.post",
        fake_post,
    )

    with pytest.raises(ProviderError):

        make_provider().chat(make_request())


def test_provider_wraps_missing_choices_as_provider_error(
    monkeypatch
):

    def fake_post(url, headers, json, timeout):

        return FakeResponse(
            200,
            json_payload={
                "model": "deepseek/deepseek-chat"
            },
        )

    monkeypatch.setattr(
        "simulation.llm.openrouter_provider.requests.post",
        fake_post,
    )

    with pytest.raises(ProviderError):

        make_provider().chat(make_request())


def test_provider_parses_valid_response(monkeypatch):

    def fake_post(url, headers, json, timeout):

        return FakeResponse(
            200,
            json_payload={
                "choices": [
                    {
                        "message": {
                            "content": "hello"
                        },
                        "finish_reason": "stop",
                    }
                ],
                "model": "deepseek/deepseek-chat",
                "usage": {
                    "total_tokens": 42
                },
            },
        )

    monkeypatch.setattr(
        "simulation.llm.openrouter_provider.requests.post",
        fake_post,
    )

    result = make_provider().chat(make_request())

    assert result.content == "hello"

    assert result.model == "deepseek/deepseek-chat"

    assert result.tokens_used == 42

    assert result.finish_reason == "stop"


def test_provider_logs_never_contain_api_key_or_response_body(
    monkeypatch,
    caplog
):

    body_marker = "UNIQUE_RESPONSE_BODY_MARKER"

    def fake_post(url, headers, json, timeout):

        return FakeResponse(
            200,
            json_payload={
                "choices": [
                    {
                        "message": {
                            "content": body_marker
                        }
                    }
                ],
                "model": "deepseek/deepseek-chat",
            },
        )

    monkeypatch.setattr(
        "simulation.llm.openrouter_provider.requests.post",
        fake_post,
    )

    caplog.set_level(logging.DEBUG)

    result = make_provider().chat(make_request())

    assert result.content == body_marker

    assert "sk-test-provider-key" not in caplog.text

    assert body_marker not in caplog.text
