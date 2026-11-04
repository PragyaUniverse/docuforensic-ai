"""Resilient LLM client: chain, retries, key rotation, caching, rate limits, counters.

complete_json never raises to its caller. On total failure it returns
LLMResult(ok=False, mode="deterministic"), and callers use their deterministic text.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from config.settings import mask, settings
from llm.providers import PROVIDERS, Provider, ProviderError, schema_hint
from llm.redact import redact, scrub_secrets

log = logging.getLogger("docuforensic.llm")

SYSTEM_BASE = (
    "You assist a human document examiner. Respond with one JSON object only, matching this JSON "
    "schema: {schema}. Do not add markdown. Use only facts in the user message; never invent values."
)
COOLDOWN_S = {"rate_limit": 60.0, "auth": 3600.0, "network": 30.0, "timeout": 60.0, "server": 30.0}


@dataclass
class LLMResult:
    ok: bool
    mode: str  # "live_llm" | "demo_cache" | "deterministic"
    data: Any = None
    provider: str | None = None
    model: str | None = None
    prompt_hash: str | None = None
    cached: bool = False
    error: str | None = None
    tried: list[str] = field(default_factory=list)
    tokens: int = 0


def _extract_json(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        return fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


class _RateLimiter:
    def __init__(self) -> None:
        self._next: dict[str, float] = {}
        self._lock = threading.Lock()

    def delay(self, provider: Provider) -> float:
        interval = 60.0 / max(provider.rpm, 1)
        with self._lock:
            now = time.monotonic()
            at = max(self._next.get(provider.name, 0.0), now)
            self._next[provider.name] = at + interval
            return at - now


class LLMClient:
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(timeout=settings.llm_timeout_s, transport=transport)
        self._limiter = _RateLimiter()
        self._lock = threading.Lock()
        self._cooldown: dict[str, float] = {}
        self._key_index: dict[str, int] = {}
        self._dead_keys: set[str] = set()
        self._last: dict[str, dict[str, Any]] = {}
        self.usage: dict[str, Any] = {"calls": 0, "tokens": 0, "cache_hits": 0, "by_provider": {}}
        self.record_demo = False  # scripts/warm_cache.py sets this during real runs
        self._sleep = time.sleep

    # ---- caching
    @staticmethod
    def prompt_hash(task: str, system: str, prompt: str, schema: type[BaseModel], strength: str) -> str:
        blob = json.dumps([task, system, prompt, schema_hint(schema), strength], ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()

    @staticmethod
    def _runtime_cache_dir() -> Path:
        return Path(settings.data_dir) / "llm_cache"

    def _read(self, directory: Path, key: str, schema: type[BaseModel]) -> dict | None:
        path = directory / f"{key}.json"
        try:
            entry = json.loads(path.read_text("utf-8"))
            entry["data"] = schema.model_validate(entry["answer"])
            return entry
        except (OSError, ValueError, KeyError, ValidationError):
            return None

    def _write(self, directory: Path, key: str, task: str, data: BaseModel, provider: str,
               model: str) -> None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            entry = {
                "task": task, "provider": provider, "model": model,
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "answer": data.model_dump(mode="json"),
            }
            (directory / f"{key}.json").write_text(
                json.dumps(entry, indent=1, ensure_ascii=False), "utf-8")
        except OSError as exc:
            log.warning("llm cache write failed: %s", type(exc).__name__)

    # ---- bookkeeping
    def _count(self, provider: str, tokens: int = 0, error: bool = False) -> None:
        with self._lock:
            per = self.usage["by_provider"].setdefault(provider, {"calls": 0, "tokens": 0, "errors": 0})
            per["calls"] += 1
            per["tokens"] += tokens
            per["errors"] += int(error)
            self.usage["calls"] += 1
            self.usage["tokens"] += tokens

    def _note(self, provider: str, ok: bool, detail: str, model: str | None = None) -> None:
        self._last[provider] = {"ok": ok, "detail": scrub_secrets(detail), "model": model}

    def _keys(self, provider: Provider) -> list[str | None]:
        if not provider.needs_key:
            return [None]
        keys = [k for k in settings.keys_for(provider.name) if k not in self._dead_keys]
        start = self._key_index.get(provider.name, 0) % max(len(keys), 1)
        return keys[start:] + keys[:start]

    def _usable(self, provider: Provider) -> tuple[bool, str]:
        if settings.offline and provider.external:
            return False, "offline mode"
        if self._cooldown.get(provider.name, 0.0) > time.monotonic():
            return False, "cooling down"
        if provider.needs_key and not self._keys(provider):
            return False, "no key"
        if provider.name == "ollama":
            ready, detail = provider.status(self._http)  # type: ignore[attr-defined]
            if not ready:
                return False, detail
        return True, ""

    # ---- main entry
    def complete_json(
        self, task: str, prompt: str, schema: type[BaseModel],
        strength: Literal["fast", "strong"] = "fast", system: str = "",
        pii_values: list[str] | None = None,
    ) -> LLMResult:
        full_system = (system + "\n" if system else "") + SYSTEM_BASE.format(schema=schema_hint(schema))
        key = self.prompt_hash(task, full_system, prompt, schema, strength)

        if settings.demo_cache:
            entry = self._read(Path(settings.llm_cache_dir), key, schema)
            if entry:
                with self._lock:
                    self.usage["cache_hits"] += 1
                return LLMResult(True, "demo_cache", entry["data"], entry.get("provider"),
                                 entry.get("model"), key, cached=True)
        if not self.record_demo:
            entry = self._read(self._runtime_cache_dir(), key, schema)
            if entry and (not settings.offline or entry.get("provider") == "ollama"):
                with self._lock:
                    self.usage["cache_hits"] += 1
                return LLMResult(True, "live_llm", entry["data"], entry.get("provider"),
                                 entry.get("model"), key, cached=True)

        tried: list[str] = []
        last_error = "no LLM provider available"
        for name in settings.chain():
            provider = PROVIDERS.get(name)
            if provider is None:
                continue
            usable, why = self._usable(provider)
            if not usable:
                tried.append(f"{name}: skipped ({why})")
                continue
            try:
                result = self._run_provider(provider, task, full_system, prompt, schema, strength,
                                            pii_values)
            except ProviderError as exc:
                last_error = str(exc)
                tried.append(f"{name}: {exc.kind}")
                self._note(name, False, str(exc))
                self._cooldown[name] = time.monotonic() + COOLDOWN_S.get(exc.kind, 15.0)
                log.warning("llm provider failed provider=%s kind=%s", name, exc.kind)
                continue
            result.prompt_hash = key
            result.tried = tried + [f"{name}: ok"]
            self._write(self._runtime_cache_dir(), key, task, result.data, name, result.model or "")
            if self.record_demo:
                self._write(Path(settings.llm_cache_dir), key, task, result.data, name,
                            result.model or "")
            return result
        return LLMResult(False, "deterministic", prompt_hash=key, error=scrub_secrets(last_error),
                         tried=tried)

    def _run_provider(self, provider, task, system, prompt, schema, strength, pii_values) -> LLMResult:
        redaction = None
        send_prompt = prompt
        if provider.external and settings.redact_pii_external:
            redaction = redact(prompt, pii_values)
            send_prompt = redaction.text

        last: ProviderError | None = None
        keys = self._keys(provider)
        for key in keys:
            for attempt in range(settings.llm_max_retries + 1):
                wait = self._limiter.delay(provider)
                if wait > 0:
                    self._sleep(wait)
                try:
                    reply = provider.call(self._http, system, send_prompt, schema, strength, key)
                except ProviderError as exc:
                    self._count(provider.name, error=True)
                    last = exc
                    if exc.kind == "auth":
                        if key:
                            self._dead_keys.add(key)
                        log.warning("llm key rejected provider=%s key=%s", provider.name, mask(key))
                        break
                    if exc.kind == "rate_limit":
                        self._key_index[provider.name] = self._key_index.get(provider.name, 0) + 1
                        if len(keys) > 1:
                            break  # rotate immediately
                        self._sleep(min(exc.retry_after or (0.5 * 2**attempt), 5.0))
                        continue
                    if exc.kind == "client":
                        break
                    self._sleep(0.5 * 2**attempt)
                    continue

                self._count(provider.name, reply.tokens)
                text = redaction.restore(reply.text) if redaction else reply.text
                try:
                    data = schema.model_validate_json(_extract_json(text))
                except ValidationError as exc:
                    last = ProviderError("bad_output", f"{provider.name} output failed validation")
                    send_prompt += "\n\nYour previous reply was not valid JSON for the schema. " \
                                   "Reply with only the corrected JSON object."
                    continue
                self._note(provider.name, True, "last call succeeded", reply.model)
                return LLMResult(True, "live_llm", data, provider.name, reply.model,
                                 tokens=reply.tokens)
        raise last or ProviderError("network", f"{provider.name} had no usable key")

    # ---- status for /capabilities and scripts/check_keys.py
    def provider_status(self) -> list[dict[str, Any]]:
        out = []
        for name, provider in PROVIDERS.items():
            keys = settings.keys_for(name) if provider.needs_key else []
            last = self._last.get(name)
            if provider.needs_key:
                if not keys:
                    status = "unverified until a key is provided"
                elif settings.offline:
                    status = "disabled (offline mode)"
                elif last:
                    status = "working" if last["ok"] else f"failing: {last['detail']}"
                else:
                    status = "key present, not yet called"
            else:
                ready, detail = provider.status(self._http)  # type: ignore[attr-defined]
                status = f"working: {detail}" if ready and last and last["ok"] else (
                    f"available: {detail}" if ready else f"unavailable: {detail}")
            out.append({
                "provider": name,
                "key_present": bool(keys),
                "keys_masked": [mask(k) for k in keys],
                "status": status,
                "model": (last or {}).get("model") or provider.model_for("strong"),
                "external": provider.external,
            })
        return out

    def ping(self, name: str) -> dict[str, Any]:
        """One tiny real call to a provider. Used by scripts/check_keys.py."""

        class Pong(BaseModel):
            ok: bool

        provider = PROVIDERS[name]
        system = SYSTEM_BASE.format(schema=schema_hint(Pong))
        for key in self._keys(provider):
            try:
                reply = provider.call(self._http, system, 'Return {"ok": true}.', Pong, "fast", key)
                Pong.model_validate_json(_extract_json(reply.text))
                self._count(name, reply.tokens)
                self._note(name, True, "ping succeeded", reply.model)
                return {"ok": True, "detail": "working", "model": reply.model}
            except (ProviderError, ValidationError) as exc:
                self._note(name, False, str(exc))
                detail = scrub_secrets(str(exc))
        else:
            if provider.needs_key and not self._keys(provider):
                return {"ok": False, "detail": "no key", "model": provider.model_for("fast")}
        return {"ok": False, "detail": detail, "model": provider.model_for("fast")}

    def any_live_provider(self) -> bool:
        return any(self._usable(PROVIDERS[n])[0] for n in settings.chain() if n in PROVIDERS)


_client: LLMClient | None = None
_client_lock = threading.Lock()


def get_client() -> LLMClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = LLMClient()
        return _client


def reset_client(client: LLMClient | None = None) -> None:
    global _client
    with _client_lock:
        _client = client
