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


def test_false_alarm_tracker_counts_reviewer_decisions_per_check(monkeypatch, tmp_path):
    from backend import analytics
    from models.schemas import (
        Case,
        Finding,
        FindingCategory,
        FindingStatus,
        ReviewDecision,
        ReviewRecord,
        Severity,
    )

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    case = db.save_case(Case(name="T"))

    def flag(detector, decision, status=FindingStatus.INCONSISTENCY):
        db.save_finding(Finding(case_id=case.id, status=status, category=FindingCategory.visual, severity=Severity.medium,
                                confidence=0.7, title="t", explanation="e", detector=detector,
                                review=ReviewRecord(decision=decision)))

    for d in (ReviewDecision.dismissed, ReviewDecision.dismissed, ReviewDecision.confirmed, ReviewDecision.pending):
        flag("visual.noise", d)
    flag("cross.dob_mismatch", ReviewDecision.confirmed)
    flag("visual.noise", ReviewDecision.dismissed, FindingStatus.OBSERVATION)  # observations aren't flags

    rows = {r["check"]: r for r in analytics.track_record()}
    noise = rows["visual.noise"]
    assert (noise["flagged"], noise["decided"], noise["dismissed"], noise["confirmed"]) == (4, 3, 2, 1)
    assert noise["dismissal_rate"] == round(2 / 3, 3)
    assert rows["cross.dob_mismatch"]["dismissal_rate"] is None  # one decision says too little
    body = TestClient(app).get("/api/analytics/track-record").json()
    assert body["min_decisions"] == analytics.MIN_DECISIONS and len(body["checks"]) == 2
