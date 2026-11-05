"""Reads a small image crop with a local vision model. Local only: document images never leave the machine."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path

import httpx

from config.settings import settings

log = logging.getLogger("llm.vision")
PROMPT = (
    "This image is a cropped field from a form, and it may be handwritten. "
    "Reply with exactly the text written in it, and nothing else. "
    "Don't explain, and don't guess at anything you can't see. If it can't be read, reply UNREADABLE."
)


def available() -> bool:
    try:
        tags = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0).json()
    except Exception:
        return False
    return any(m.get("name", "").startswith(settings.ollama_vision_model) for m in tags.get("models", []))


def read_image(png: bytes) -> str | None:
    """The text in the crop, or None if it can't be read or no model is available."""
    key = hashlib.sha256(png + settings.ollama_vision_model.encode()).hexdigest()
    cache = Path(settings.data_dir) / "llm_cache" / f"vision_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())["text"]
    try:
        res = httpx.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_vision_model, "stream": False, "options": {"temperature": 0},
                "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(png).decode()]}],
            },
            timeout=settings.llm_timeout_s,
        )
        res.raise_for_status()
        text = res.json()["message"]["content"].strip().strip('"').strip()
    except Exception as exc:
        log.warning("vision read failed: %s", type(exc).__name__)
        return None
    # A reading is one short line. Anything else is the model talking, not the document.
    result = None if (not text or "UNREADABLE" in text.upper() or "\n" in text or len(text) > 80) else text
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"text": result}))
    return result
