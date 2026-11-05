"""Login is off by default. When on, nothing but login and health is reachable without a session."""
import pytest
from fastapi.testclient import TestClient

from backend import auth, db
from backend.app import app
from config.settings import settings

# A value made up for this test only.
PASSWORD = "a-test-only-password"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_enabled", True)
    auth.create_user("asha", PASSWORD)
    return TestClient(app)


def test_everything_needs_a_session_except_login_and_health(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/me").json() == {"auth_enabled": True, "user": None}
    for path in ("/api/cases", "/api/capabilities", "/api/analytics", "/api/files/x.png"):
        assert client.get(path).status_code == 401, path


def test_wrong_password_is_refused(client):
    assert client.post("/api/auth/login", json={"username": "asha", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "nobody", "password": PASSWORD}).status_code == 401


def test_session_lets_you_in_and_logout_ends_it(client):
    assert client.post("/api/auth/login", json={"username": "asha", "password": PASSWORD}).status_code == 200
    assert client.get("/api/cases").status_code == 200
    assert client.get("/api/auth/me").json()["user"] == "asha"
    client.post("/api/auth/logout")
    assert client.get("/api/cases").status_code == 401


def test_the_password_is_not_stored_in_clear(client):
    row = db._read("SELECT salt, hash FROM users WHERE username = 'asha'")[0]
    assert PASSWORD.encode().hex() not in row["hash"]


def test_short_passwords_are_refused(client):
    with pytest.raises(ValueError):
        auth.create_user("bob", "short")


def test_login_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "auth_enabled", False)
    c = TestClient(app)
    assert c.get("/api/cases").status_code == 200
    assert c.get("/api/auth/me").json() == {"auth_enabled": False, "user": None}
    assert c.get("/api/analytics").json()["cases"] == 0
