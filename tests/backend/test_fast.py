"""Speed: screens get small WebP copies of the same size, JSON is compressed, the live stream is not."""
import numpy as np
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from PIL import Image

from backend import fast


def test_display_copy_is_smaller_same_size_and_reused(tmp_path):
    src = tmp_path / "page_0.png"
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(200, 255, (600, 400, 3), dtype=np.uint8)).save(src)
    out = fast.display_copy(src)
    assert out.suffix == ".webp" and out.stat().st_size < src.stat().st_size
    with Image.open(out) as im:
        assert im.size == (400, 600)  # same pixels, so highlight boxes still line up
    mtime = out.stat().st_mtime_ns
    assert fast.display_copy(src) == out and out.stat().st_mtime_ns == mtime  # made once


def test_half_size_overlay_keeps_transparency(tmp_path):
    src = tmp_path / "ela_p0.png"
    Image.new("RGBA", (200, 300), (255, 0, 0, 80)).save(src)
    out = fast.display_copy(src, scale=0.5)
    with Image.open(out) as im:
        assert im.size == (100, 150) and im.mode == "RGBA"


def test_a_broken_image_falls_back_to_the_original(tmp_path):
    src = tmp_path / "bad.png"
    src.write_bytes(b"not an image")
    assert fast.display_copy(src) == src


def _app():
    app = FastAPI()
    app.add_middleware(fast.CompressText)
    app.add_middleware(fast.CacheAssets)

    @app.get("/api/data")
    def data():
        return JSONResponse({"x": "a" * 5000})

    @app.get("/api/cases/c/progress")
    def progress():
        return StreamingResponse(iter([b"event: progress\ndata: " + b"a" * 5000 + b"\n\n"]), media_type="text/event-stream")

    @app.get("/assets/app.js")
    def asset():
        return JSONResponse({"js": True})

    return TestClient(app)


def test_json_is_gzipped_but_the_progress_stream_is_not():
    client = _app()
    assert client.get("/api/data", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding") == "gzip"
    assert "content-encoding" not in client.get("/api/cases/c/progress", headers={"Accept-Encoding": "gzip"}).headers


def test_hashed_assets_are_cached_for_a_year():
    assert "immutable" in _app().get("/assets/app.js").headers["cache-control"]
