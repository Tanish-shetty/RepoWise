import json
from abc import ABC, abstractmethod
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    async def structured(self, system: str, user: str, schema: type[T]) -> T:
        """Return validated structured output or raise a controlled error."""


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model

    async def structured(self, system: str, user: str, schema: type[T]) -> T:
        if not self.api_key:
            raise LLMError("LLM API key is not configured")
        prompt = user + "\nReturn only JSON matching this schema:\n" + json.dumps(schema.model_json_schema())
        payload = {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(2):
                response = await client.post(f"{self.base_url}/chat/completions", json=payload,
                                             headers={"Authorization": f"Bearer {self.api_key}"})
                if response.status_code == 429:
                    raise LLMError("LLM rate limit reached")
                if response.is_error:
                    raise LLMError(f"LLM request failed ({response.status_code})")
                try:
                    return schema.model_validate_json(response.json()["choices"][0]["message"]["content"])
                except (KeyError, ValidationError, ValueError) as exc:
                    if attempt:
                        raise LLMError("LLM returned invalid structured output") from exc
                    payload["messages"].append({"role": "user", "content": "The response was invalid. Return only schema-compliant JSON."})
        raise LLMError("LLM request failed")


class DisabledProvider(LLMProvider):
    async def structured(self, system: str, user: str, schema: type[T]) -> T:
        raise LLMError("LLM is disabled; deterministic analysis remains available")


def create_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.llm_provider == "groq":
        return OpenAICompatibleProvider("https://api.groq.com/openai/v1", settings.groq_api_key, settings.groq_model)
    if settings.llm_provider == "openai":
        return OpenAICompatibleProvider(settings.openai_base_url, settings.openai_api_key, settings.openai_model)
    return DisabledProvider()

