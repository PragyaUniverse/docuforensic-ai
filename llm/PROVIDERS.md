# LLM providers (free tiers only)

Checked against official pages on 4 Nov 2026. Free limits change often, so model ids are settings
(`GEMINI_MODEL_FAST`, `GEMINI_MODEL_STRONG`, and so on) and `scripts/check_keys.py` reports what
really works with your key.

**No remote provider has been called with a real key by this project yet. Only mocked HTTP tests
exist for Gemini, Groq and OpenRouter until a key is provided.** Ollama has been run live.

| Provider | Fast model (default) | Strong model (default) | Free limits as documented | Key |
|---|---|---|---|---|
| Gemini | `gemini-3.5-flash-lite` | `gemini-3.6-flash` | Google no longer publishes per-model free figures; see your project's limits in AI Studio. Limits are per project, not per key, so extra keys from one project don't add quota. | https://aistudio.google.com/apikey |
| Groq | `llama-3.1-8b-instant` | `openai/gpt-oss-120b` | Docs publish Developer-plan limits only (for example `openai/gpt-oss-120b`: 30 RPM, 1K RPD, 8K TPM, 200K TPD). See `/settings/limits` for free values. | https://console.groq.com/keys |
| OpenRouter | `google/gemma-4-26b-a4b-it:free` | `google/gemma-4-31b-it:free` | `:free` models: 20 RPM; 50 requests/day under 10 credits purchased, 1,000/day at 10 or more. | https://openrouter.ai/keys |
| Ollama | `OLLAMA_MODEL` (default `qwen2.5:7b`) | same | Local: no key, no quota | https://ollama.com |

Sources: [Gemini models](https://aistudio.google.com/docs/models),
[Gemini rate limits](https://aistudio.google.com/docs/rate-limits),
[Groq models](https://console.groq.com/docs/models),
[Groq rate limits](https://console.groq.com/docs/rate-limits),
[OpenRouter limits](https://openrouter.ai/docs/api-reference/limits); the free OpenRouter ids came
from its public `/api/v1/models` listing on the same date.

Client-side limits in `llm/providers.py` are deliberately conservative. Hugging Face and Mistral
keys are accepted by settings, but they have no adapter yet.
