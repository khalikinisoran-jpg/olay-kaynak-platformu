from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    role: str
    content: str


@dataclass
class LLMRequest:
    messages: list[Message]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int
    finish_reason: str