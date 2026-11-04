"""Human oversight and the tamper-evident audit trail."""
from __future__ import annotations

from itertools import pairwise

import pytest

from config.settings import settings


@pytest.fixture(scope="module")
def tampered_case(client):
    """Demo case B, run once for the module."""
    from tests.conftest import Api

    api = Api(client)
    case_id = api.load_demo("case_b")
    if case_id is None:
        pytest.skip("demo case B not available yet")
    api.run(case_id)
    return case_id


def test_each_review_decision_persists_and_is_audited(api, tampered_case):
    findings = api.findings(tampered_case)
    assert len(findings) >= 3, "case B has injected manipulations; expected several findings"
    for finding, decision in zip(findings, ("confirmed", "dismissed", "escalated"), strict=False):
        res = api.client.post(
            f"/api/findings/{finding['id']}/review",
            json={"decision": decision, "reviewer": "e2e-reviewer", "note": "checked"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["review"]["decision"] == decision
        assert res.json()["review"]["reviewer"] == "e2e-reviewer"

        stored = next(f for f in api.findings(tampered_case) if f["id"] == finding["id"])
        assert stored["review"]["decision"] == decision

    audit = api.client.get(f"/api/cases/{tampered_case}/audit").json()
    reviewed = [e for e in audit if "review" in e["action"]]
    assert len(reviewed) >= 3
    assert any(e["actor"].endswith("e2e-reviewer") for e in reviewed)


def test_review_does_not_rewrite_the_finding_itself(api, tampered_case):
    before = api.findings(tampered_case)[0]
    res = api.client.post(
        f"/api/findings/{before['id']}/review",
        json={"decision": "dismissed", "reviewer": "r", "note": "n"},
    )
    after = res.json()
    for key in ("status", "severity", "confidence", "bbox", "detector", "explanation"):
        assert after[key] == before[key], key


def test_invalid_review_is_rejected(api, tampered_case):
    finding = api.findings(tampered_case)[0]
    res = api.client.post(f"/api/findings/{finding['id']}/review",
                          json={"decision": "looks_forged", "reviewer": "r"})
    assert res.status_code == 422
    res = api.client.post("/api/findings/fnd_missing/review",
                          json={"decision": "confirmed", "reviewer": "r"})
    assert res.status_code == 404


def test_pipeline_stages_are_audited(api, tampered_case):
    entries = api.client.get(f"/api/cases/{tampered_case}/audit").json()
    assert entries, "the case has an audit trail"
    actions = " ".join(e["action"] for e in entries).lower()
    for word in ("submi", "classif", "ocr", "visual", "cross", "dossier"):
        assert word in actions, f"no audit entry mentions {word}"
    for older, newer in pairwise(entries):
        assert newer["seq"] > older["seq"]


def test_audit_verifies_then_fails_when_tampered_then_recovers(api, tampered_case):
    if not settings.audit_tamper_demo:
        pytest.skip("tamper demo disabled")
    verify = f"/api/cases/{tampered_case}/audit/verify"
    clean = api.client.get(verify).json()
    assert clean["ok"] is True
    assert clean["entries_checked"] > 0
    assert clean["head_hash"]

    tampered = api.client.post("/api/audit/tamper-demo")
    assert tampered.status_code == 200, tampered.text
    seq = tampered.json()["tampered_seq"]
    try:
        bad = api.client.get(verify).json()
        assert bad["ok"] is False, "editing a stored entry must break verification"
        assert bad["first_bad_seq"] == seq
        assert bad["reason"]
    finally:
        assert api.client.post("/api/audit/tamper-demo/restore").status_code == 200
    assert api.client.get(verify).json()["ok"] is True


def test_tamper_endpoint_is_off_when_disabled(api, monkeypatch):
    monkeypatch.setattr(settings, "audit_tamper_demo", False)
    assert api.client.post("/api/audit/tamper-demo").status_code in (403, 404)


def test_chain_links_each_entry_to_the_previous_hash():
    """Direct check on the chain, independent of the demo endpoint."""
    chain = pytest.importorskip("audit.chain", reason="audit chain not landed yet")
    first = chain.append("test.one", "system", payload={"n": 1})
    second = chain.append("test.two", "system", payload={"n": 2})
    assert second.prev_hash == first.entry_hash
    assert second.seq == first.seq + 1
    assert chain.verify().ok is True
