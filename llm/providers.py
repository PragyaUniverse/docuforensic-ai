"""Provider adapters. Each turns (system, prompt, schema) into JSON text over HTTP."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel

from config.settings import settings
from llm.redact import scrub_secrets

Strength = Literal["fast", "strong"]


class ProviderError(Exception):
    """kind: rate_limit | auth | timeout | network | server | bad_output | client."""

    def __init__(self, kind: str, message: str, retry_after: float | None = None):
        super().__init__(scrub_secrets(message))
        self.kind = kind
        self.retry_after = retry_after


@dataclass
class ProviderReply:
    text: str
    model: str
    tokens: int


def _raise_for_status(resp: httpx.Response, provider: str) -> None:
    code = resp.status_code
    if code < 400:
        return
    # Never echo a provider body or URL verbatim: it could contain the key.
    msg = f"{provider} returned HTTP {code}"
    if code == 429:
        retry = resp.headers.get("retry-after")
        try:
            retry_s = float(retry) if retry else None
        except ValueError:
            retry_s = None
        raise ProviderError("rate_limit", msg, retry_s)
    if code in (401, 403):
        raise ProviderError("auth", msg)
    if code >= 500:
        raise ProviderError("server", msg)
    raise ProviderError("client", msg)


def _post(client: httpx.Client, provider: str, url: str, **kwargs) -> dict:
    try:
        resp = client.post(url, **kwargs)
    except httpx.TimeoutException as exc:
        raise ProviderError("timeout", f"{provider} timed out") from exc
    except httpx.HTTPError as exc:
        raise ProviderError("network", f"{provider} unreachable: {type(exc).__name__}") from exc
    _raise_for_status(resp, provider)
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError("bad_output", f"{provider} returned non-JSON HTTP body") from exc


class Provider:
    name = "base"
    external = True
    needs_key = True
    rpm = 10
    defaults: dict[str, str] = {}

    def model_for(self, strength: Strength) -> str:
        override = getattr(settings, f"{self.name}_model_{strength}", "")
        return override or self.defaults[strength]

    def call(
        self, client: httpx.Client, system: str, prompt: str, schema: type[BaseModel],
        strength: Strength, key: str | None,
    ) -> ProviderReply:
        raise NotImplementedError


class GeminiProvider(Provider):
    name = "gemini"
    rpm = 10
    defaults = {"fast": "gemini-3.5-flash-lite", "strong": "gemini-3.6-flash"}
    base = "https://generativelanguage.googleapis.com/v1beta/models"

    def call(self, client, system, prompt, schema, strength, key):
        model = self.model_for(strength)
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        # The key goes in a header so it can't appear in a URL inside an exception or log.
        data = _post(client, self.name, f"{self.base}/{model}:generateContent",
                     json=body, headers={"x-goog-api-key": key or ""})
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("bad_output", "gemini reply had no text candidate") from exc
        tokens = int((data.get("usageMetadata") or {}).get("totalTokenCount") or 0)
        return ProviderReply(text, model, tokens)


class _OpenAICompatible(Provider):
    url = ""
    extra_headers: dict[str, str] = {}

    def call(self, client, system, prompt, schema, strength, key):
        model = self.model_for(strength)
        body = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {key}", **self.extra_headers}
        data = _post(client, self.name, self.url, json=body, headers=headers)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("bad_output", f"{self.name} reply had no message") from exc
        tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
        return ProviderReply(text or "", model, tokens)


class GroqProvider(_OpenAICompatible):
    name = "groq"
    rpm = 25
    defaults = {"fast": "llama-3.1-8b-instant", "strong": "openai/gpt-oss-120b"}
    url = "https://api.groq.com/openai/v1/chat/completions"


class OpenRouterProvider(_OpenAICompatible):
    name = "openrouter"
    rpm = 15
    defaults = {"fast": "google/gemma-4-26b-a4b-it:free", "strong": "google/gemma-4-31b-it:free"}
    url = "https://openrouter.ai/api/v1/chat/completions"
    extra_headers = {"X-Title": "DocuForensic AI"}


class OllamaProvider(Provider):
    name = "ollama"
    external = False
    needs_key = False
    rpm = 600

    def model_for(self, strength: Strength) -> str:
        return settings.ollama_model

    def status(self, client: httpx.Client) -> tuple[bool, str]:
        """Real check of the local server and whether the model is pulled."""
        try:
            resp = client.get(f"{settings.ollama_base_url}/api/tags", timeout=1.5)
            names = [m.get("name", "") for m in resp.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            return False, "Ollama server not reachable"
        if settings.ollama_model in names:
            return True, f"model {settings.ollama_model} ready"
        return False, f"server up, model {settings.ollama_model} not pulled"

    def call(self, client, system, prompt, schema, strength, key):
        model = self.model_for(strength)
        body = {
            "model": model,
            "stream": False,
            "format": schema.model_json_schema(),
            "options": {"temperature": 0, "seed": 7},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        data = _post(client, self.name, f"{settings.ollama_base_url}/api/chat", json=body)
        if data.get("error"):
            raise ProviderError("client", "ollama reported an error")
        text = (data.get("message") or {}).get("content", "")
        tokens = int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)
        return ProviderReply(text, model, tokens)


PROVIDERS: dict[str, Provider] = {
    p.name: p for p in (GeminiProvider(), GroqProvider(), OpenRouterProvider(), OllamaProvider())
}


def schema_hint(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), sort_keys=True)
