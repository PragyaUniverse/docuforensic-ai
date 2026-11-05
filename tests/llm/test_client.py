import json
import shutil

import httpx
import pytest
from pydantic import BaseModel

from config.settings import settings
from llm.client import LLMClient


class Answer(BaseModel):
    value: str


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "llm_cache_dir", tmp_path / "demo")
    monkeypatch.setattr(settings, "offline", False)
    monkeypatch.setattr(settings, "demo_cache", False)
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    monkeypatch.setattr(settings, "ollama_base_url", "http://ollama.test")
    monkeypatch.setattr(settings, "gemini_api_keys", "")
    monkeypatch.setattr(settings, "groq_api_keys", "")
    monkeypatch.setattr(settings, "openrouter_api_keys", "")
    monkeypatch.setattr(settings, "llm_chain", "gemini,groq,openrouter,ollama")


def gemini_ok(value='{"value": "gem"}'):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": value}]}}],
                                     "usageMetadata": {"totalTokenCount": 11}})


def openai_ok(value='{"value": "oai"}'):
    return httpx.Response(200, json={"choices": [{"message": {"content": value}}], "usage": {"total_tokens": 7}})


def make(handler):
    client = LLMClient(transport=httpx.MockTransport(handler))
    client._sleep = lambda s: None
    return client


def down_ollama(request):
    if "ollama.test" in request.url.host:
        raise httpx.ConnectError("refused")


def test_no_keys_and_no_ollama_is_deterministic_without_error():
    client = make(lambda r: down_ollama(r) or httpx.Response(500))
    result = client.complete_json("t", "p", Answer)
    assert result.ok is False and result.mode == "deterministic" and result.data is None


def test_gemini_success_uses_header_not_url(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000")
    seen = []

    def handler(request):
        seen.append(request)
        return gemini_ok()

    result = make(handler).complete_json("t", "p", Answer)
    assert result.ok and result.provider == "gemini" and result.data.value == "gem" and result.mode == "live_llm"
    assert "AIza" not in str(seen[0].url) and seen[0].headers["x-goog-api-key"] == "AIzaKEYONE000000"
    assert json.loads(seen[0].content)["generationConfig"]["temperature"] == 0


def test_rate_limit_rotates_to_the_next_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000,AIzaKEYTWO000000")
    used = []

    def handler(request):
        key = request.headers["x-goog-api-key"]
        used.append(key)
        return httpx.Response(429) if key.startswith("AIzaKEYONE") else gemini_ok()

    result = make(handler).complete_json("t", "p", Answer)
    assert result.ok and used == ["AIzaKEYONE000000", "AIzaKEYTWO000000"]


def test_falls_through_chain_on_outage_and_invalid_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000")
    monkeypatch.setattr(settings, "groq_api_keys", "gsk_abcdefghij123456")
    monkeypatch.setattr(settings, "openrouter_api_keys", "sk-or-abcdefghij1234")

    def handler(request):
        if "googleapis" in request.url.host:
            return httpx.Response(403, text="bad key AIzaKEYONE000000")
        if "groq" in request.url.host:
            raise httpx.ConnectError("network down")
        return openai_ok()

    result = make(handler).complete_json("t", "p", Answer)
    assert result.ok and result.provider == "openrouter"
    assert any("gemini: auth" in t for t in result.tried) and any("groq: network" in t for t in result.tried)
    assert "AIzaKEYONE000000" not in " ".join(result.tried)


def test_all_providers_failing_never_raises_or_leaks(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaSECRET0000000")

    def handler(request):
        down_ollama(request)
        return httpx.Response(500, text="AIzaSECRET0000000")

    client = make(handler)
    result = client.complete_json("t", "p", Answer)
    assert not result.ok and "AIzaSECRET0000000" not in (result.error or "")
    status = client.provider_status()
    assert "AIzaSECRET0000000" not in json.dumps(status)
    assert next(p for p in status if p["provider"] == "gemini")["keys_masked"] == ["AIza****"]


def test_invalid_json_is_retried_then_next_provider(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000")
    monkeypatch.setattr(settings, "groq_api_keys", "gsk_abcdefghij123456")

    def handler(request):
        return gemini_ok("not json") if "googleapis" in request.url.host else openai_ok()

    result = make(handler).complete_json("t", "p", Answer)
    assert result.ok and result.provider == "groq"


def test_external_prompt_is_redacted_and_answer_restored(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000")
    sent = {}

    def handler(request):
        sent["body"] = request.content.decode()
        return gemini_ok('{"value": "about [PII_1] and [PAN_1]"}')

    result = make(handler).complete_json("t", "Priya Menon has PAN ZZAPM4821K", Answer, pii_values=["Priya Menon"])
    assert "Priya Menon" not in sent["body"] and "ZZAPM4821K" not in sent["body"]
    assert result.data.value == "about Priya Menon and ZZAPM4821K"


def test_local_ollama_receives_the_prompt_and_schema(monkeypatch):
    monkeypatch.setattr(settings, "ollama_model", "m:1")
    sent = {}

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "m:1"}]})
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"value": "local"}'}, "eval_count": 5, "prompt_eval_count": 3})

    client = make(handler)
    result = client.complete_json("t", "Priya Menon", Answer, pii_values=["Priya Menon"])
    assert result.provider == "ollama" and result.tokens == 8
    assert "Priya Menon" in sent["messages"][1]["content"] and sent["options"]["temperature"] == 0
    assert sent["format"]["properties"]["value"]


def test_offline_skips_external_but_allows_ollama(monkeypatch):
    monkeypatch.setattr(settings, "offline", True)
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000")
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": settings.ollama_model}]})
        return httpx.Response(200, json={"message": {"content": '{"value": "local"}'}})

    result = make(handler).complete_json("t", "p", Answer)
    assert result.provider == "ollama" and set(hosts) == {"ollama.test"}


def test_second_call_comes_from_cache_and_counts(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000")
    calls = []

    def handler(request):
        calls.append(1)
        return gemini_ok()

    client = make(handler)
    first = client.complete_json("t", "p", Answer)
    second = client.complete_json("t", "p", Answer)
    assert len(calls) == 1 and second.cached and second.data == first.data
    assert client.usage["cache_hits"] == 1 and client.usage["tokens"] == 11
    assert client.usage["by_provider"]["gemini"]["calls"] == 1


def test_demo_cache_replays_only_recorded_answers(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000")
    client = make(lambda r: gemini_ok())
    client.record_demo = True
    client.complete_json("t", "p", Answer)
    assert list((settings.llm_cache_dir).glob("*.json"))

    monkeypatch.setattr(settings, "gemini_api_keys", "")
    monkeypatch.setattr(settings, "demo_cache", True)
    replay = make(lambda r: down_ollama(r) or httpx.Response(500))
    hit = replay.complete_json("t", "p", Answer)
    assert hit.ok and hit.mode == "demo_cache" and hit.provider == "gemini"
    miss = replay.complete_json("t", "a different prompt", Answer)
    assert not miss.ok and miss.mode == "deterministic"


def test_capabilities_label_without_key_is_honest():
    status = make(lambda r: down_ollama(r) or httpx.Response(500)).provider_status()
    gem = next(p for p in status if p["provider"] == "gemini")
    assert gem["status"] == "unverified until a key is provided" and gem["key_present"] is False


def test_recorded_answers_are_replayed_when_every_provider_is_down(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_keys", "AIzaKEYONE000000")
    client = make(lambda r: gemini_ok())
    client.record_demo = True
    client.complete_json("t", "p", Answer)
    # A fresh clone has the recorded answers but no local cache of its own.
    shutil.rmtree(client._runtime_cache_dir())

    monkeypatch.setattr(settings, "gemini_api_keys", "")
    replay = make(lambda r: down_ollama(r) or httpx.Response(500))
    hit = replay.complete_json("t", "p", Answer)
    assert hit.ok and hit.mode == "demo_cache", "must be labelled as a replay, never as live"
    # Different evidence has no recorded answer, so nothing is invented.
    miss = replay.complete_json("t", "a different prompt", Answer)
    assert not miss.ok and miss.mode == "deterministic"
