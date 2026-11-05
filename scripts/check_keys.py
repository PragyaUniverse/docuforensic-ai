#!/usr/bin/env python
"""Tests each configured LLM provider with one tiny call and prints a table. Keys stay masked."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import mask, settings
from llm.client import get_client
from llm.providers import PROVIDERS

LINKS = {
    "gemini": "https://aistudio.google.com/apikey", "groq": "https://console.groq.com/keys",
    "openrouter": "https://openrouter.ai/keys", "ollama": "https://ollama.com (local, no key)",
}


def main() -> int:
    client = get_client()
    rows = [("Provider", "Key", "Result", "Free model used")]
    working = 0
    for name, provider in PROVIDERS.items():
        keys = settings.keys_for(name) if provider.needs_key else []
        shown = ", ".join(mask(k) for k in keys) if keys else ("not needed" if not provider.needs_key else "missing")
        if settings.offline and provider.external:
            result, model = "skipped (OFFLINE=true)", provider.model_for("fast")
        elif provider.needs_key and not keys:
            result, model = f"unverified: add a key from {LINKS[name]}", provider.model_for("fast")
        else:
            if name == "ollama":
                ready, detail = provider.status(client._http)  # type: ignore[attr-defined]
                if not ready:
                    rows.append((name, shown, f"unavailable: {detail}", provider.model_for("fast")))
                    continue
            ping = client.ping(name)
            result, model = ("working" if ping["ok"] else f"failing: {ping['detail']}"), ping["model"]
            working += int(ping["ok"])
        rows.append((name, shown, result, model))

    widths = [max(len(str(r[i])) for r in rows) for i in range(4)]
    for i, row in enumerate(rows):
        print("  ".join(str(c).ljust(widths[j]) for j, c in enumerate(row)))
        if i == 0:
            print("  ".join("-" * w for w in widths))
    print(f"\n{working} provider(s) working. With none, the app still runs: "
          "local forensics plus deterministic reasoning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
