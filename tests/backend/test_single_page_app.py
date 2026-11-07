"""The built website is served by the API, so deep links must load the app, not a 404."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import _SinglePageApp


def _client(tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    app.mount("/", _SinglePageApp(directory=tmp_path, html=True), name="frontend")
    return TestClient(app)


def test_deep_links_load_the_app(tmp_path):
    client = _client(tmp_path)
    for path in ("/", "/cases/case_123", "/cases/case_123/viewer", "/capabilities"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "id=root" in r.text, path


def test_real_files_and_api_routes_are_unchanged(tmp_path):
    client = _client(tmp_path)
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/api/health").json() == {"status": "ok"}


def test_unknown_paths_stay_a_404(tmp_path):
    client = _client(tmp_path)
    for path in ("/api/does-not-exist", "/etc/passwd", "/assets/missing.js"):
        r = client.get(path)
        assert r.status_code == 404, path
        assert r.json() == {"detail": "Not Found"}, path
