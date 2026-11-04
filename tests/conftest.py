"""Shared test setup: isolated state, no keys, no network.

Environment variables are set here, before anything imports config.settings, because settings are
built once at import. Real environment variables take priority over .env, so a developer's real
keys can never reach a test. Port 9 (discard) is a dead local address, which makes Ollama a real
outage for tests, not a mock.
"""
from __future__ import annotations

import atexit
import io
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="docuforensic-test-"))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

os.environ.update(
    {
        "DATA_DIR": str(_TMP / "data"),
        "LLM_CACHE_DIR": str(_TMP / "llm_cache"),
        "GEMINI_API_KEYS": "",
        "GROQ_API_KEYS": "",
        "OPENROUTER_API_KEYS": "",
        "HUGGINGFACE_API_KEYS": "",
        "MISTRAL_API_KEYS": "",
        "OLLAMA_BASE_URL": "http://127.0.0.1:9",
        "OFFLINE": "true",
        "DEMO_CACHE": "false",
        "LLM_MAX_RETRIES": "0",
        "LLM_TIMEOUT_S": "1",
        "RATE_LIMIT_PER_MINUTE": "100000",
    }
)

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_MODULES = ("backend.main", "backend.app", "backend.api")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def data_dir() -> Path:
    from config.settings import settings

    return Path(settings.data_dir)


def _load_app():
    import importlib

    last: Exception | None = None
    for name in APP_MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            # A missing dependency inside an existing module is a bug, not "not built yet".
            if exc.name and not name.startswith(exc.name):
                raise
            last = exc
            continue
        if hasattr(module, "app"):
            return module.app
    pytest.skip(f"FastAPI app not available yet (tried {', '.join(APP_MODULES)}): {last}")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False: an unhandled error must surface as an HTTP 500 we can assert
    # on, the way a real client would see it.
    with TestClient(_load_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def api(client):
    return Api(client)


class Api:
    """Small helper over the REST contract in docs/CONTRACTS.md section 3."""

    def __init__(self, client):
        self.client = client

    def create_case(self, name: str = "e2e") -> str:
        res = self.client.post("/api/cases", json={"name": name})
        assert res.status_code in (200, 201), res.text
        return res.json()["id"]

    def upload(self, case_id: str, *files: tuple[str, bytes, str]):
        payload = [("files", (name, data, mime)) for name, data, mime in files]
        return self.client.post(f"/api/cases/{case_id}/documents", files=payload)

    def run(self, case_id: str, timeout: float = 180.0) -> dict:
        res = self.client.post(f"/api/cases/{case_id}/run")
        assert res.status_code in (200, 202), res.text
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            body = self.client.get(f"/api/cases/{case_id}").json()
            if body["case"]["status"] in ("complete", "failed"):
                return body
            time.sleep(0.2)
        pytest.fail(f"case {case_id} did not finish in {timeout}s")

    def findings(self, case_id: str) -> list[dict]:
        res = self.client.get(f"/api/cases/{case_id}/findings")
        assert res.status_code == 200, res.text
        return res.json()

    def load_demo(self, match: str) -> str | None:
        res = self.client.get("/api/demo-cases")
        if res.status_code != 200:
            return None
        for case in res.json():
            if match in case["key"]:
                loaded = self.client.post(f"/api/demo-cases/{case['key']}/load")
                assert loaded.status_code in (200, 201), loaded.text
                return loaded.json()["id"]
        return None


def synthetic_document_png(lines: list[str] | None = None, size=(1654, 2339)) -> bytes:
    """A small synthetic document, watermarked SYNTHETIC like all project data."""
    import reportlab
    from PIL import Image, ImageDraw, ImageFont
    from reportlab import rl_config  # noqa: F401

    font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    font = ImageFont.truetype(str(font_path), 34)
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    text = lines or [
        "SYNTHETIC SAMPLE - NOT A REAL DOCUMENT",
        "SALARY SLIP",
        "Employee Name: Asha Testperson",
        "Employer: Example Widgets Pvt Ltd",
        "Pay Period: March 2026",
        "Basic Pay: 40,000.00",
        "Gross Pay: 60,000.00",
        "Total Deductions: 10,000.00",
        "Net Pay: 50,000.00",
    ]
    for i, line in enumerate(text):
        draw.text((120, 140 + i * 90), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def noise_png(size=(800, 600), seed: int = 7) -> bytes:
    """Pure noise: no readable text, so OCR confidence or coverage has to be poor."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype="uint8")
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def document_png() -> bytes:
    return synthetic_document_png()
